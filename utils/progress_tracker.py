# utils/progress_tracker.py
import time
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import threading

from ..config.settings import settings


class ProgressStatus(Enum):
    """Statuts de progression"""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressStep:
    """Représente une étape de progression"""
    name: str
    description: str = ""
    total_items: int = 0
    completed_items: int = 0
    status: ProgressStatus = ProgressStatus.NOT_STARTED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def progress_percentage(self) -> float:
        """Calcule le pourcentage de progression"""
        if self.total_items == 0:
            return 0.0
        return (self.completed_items / self.total_items) * 100
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Calcule la durée de l'étape"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return datetime.now() - self.start_time
        return None
    
    @property
    def estimated_time_remaining(self) -> Optional[timedelta]:
        """Estime le temps restant"""
        if not self.start_time or self.completed_items == 0:
            return None
        
        elapsed = datetime.now() - self.start_time
        rate = self.completed_items / elapsed.total_seconds()
        remaining_items = self.total_items - self.completed_items
        
        if rate > 0 and remaining_items > 0:
            remaining_seconds = remaining_items / rate
            return timedelta(seconds=remaining_seconds)
        
        return None
    
    def start(self):
        """Démarre l'étape"""
        self.status = ProgressStatus.RUNNING
        self.start_time = datetime.now()
    
    def complete(self):
        """Marque l'étape comme terminée"""
        self.status = ProgressStatus.COMPLETED
        self.end_time = datetime.now()
        self.completed_items = self.total_items
    
    def fail(self, error_message: str = None):
        """Marque l'étape comme échouée"""
        self.status = ProgressStatus.FAILED
        self.end_time = datetime.now()
        if error_message:
            self.errors.append(error_message)
    
    def add_error(self, error_message: str):
        """Ajoute une erreur à l'étape"""
        self.errors.append(error_message)
    
    def update_progress(self, completed: int, total: Optional[int] = None):
        """Met à jour la progression"""
        self.completed_items = completed
        if total is not None:
            self.total_items = total


class ProgressTracker:
    """
    Tracker de progression pour les opérations longues.
    
    Fonctionnalités:
    - Suivi multi-étapes
    - Estimation du temps restant
    - Callbacks pour les mises à jour
    - Thread-safe
    - Gestion des erreurs et reprises
    """
    
    def __init__(self, session_id: str, operation_name: str = "Operation"):
        self.session_id = session_id
        self.operation_name = operation_name
        self.steps: Dict[str, ProgressStep] = {}
        self.current_step: Optional[str] = None
        self.status = ProgressStatus.NOT_STARTED
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # Configuration
        self.auto_save_interval = settings.get('sessions.auto_save_interval', 60)
        self.update_callbacks: List[Callable] = []
        
        # Thread safety
        self._lock = threading.Lock()
        self._last_save = datetime.now()
        
        # Métriques globales
        self.total_operations = 0
        self.completed_operations = 0
        self.failed_operations = 0
        self.success_rate = 0.0
        
        print(f"🎯 Tracker de progression initialisé: {operation_name}")
    
    def add_step(self, step_name: str, description: str = "", total_items: int = 0) -> ProgressStep:
        """Ajoute une nouvelle étape"""
        with self._lock:
            step = ProgressStep(
                name=step_name,
                description=description,
                total_items=total_items
            )
            self.steps[step_name] = step
            print(f"📝 Étape ajoutée: {step_name} ({total_items} éléments)")
            return step
    
    def start_operation(self):
        """Démarre l'opération globale"""
        with self._lock:
            self.status = ProgressStatus.RUNNING
            self.start_time = datetime.now()
            print(f"🚀 Début de l'opération: {self.operation_name}")
            self._notify_callbacks()
    
    def start_step(self, step_name: str) -> ProgressStep:
        """Démarre une étape spécifique"""
        with self._lock:
            if step_name not in self.steps:
                raise ValueError(f"Étape '{step_name}' non trouvée")
            
            # Terminer l'étape précédente si nécessaire
            if self.current_step and self.current_step != step_name:
                prev_step = self.steps[self.current_step]
                if prev_step.status == ProgressStatus.RUNNING:
                    prev_step.complete()
            
            self.current_step = step_name
            step = self.steps[step_name]
            step.start()
            
            print(f"▶️ Début de l'étape: {step_name}")
            self._notify_callbacks()
            return step
    
    def update_step_progress(self, step_name: str, completed: int, total: Optional[int] = None):
        """Met à jour la progression d'une étape"""
        with self._lock:
            if step_name not in self.steps:
                return
            
            step = self.steps[step_name]
            step.update_progress(completed, total)
            
            # Auto-save périodique
            if (datetime.now() - self._last_save).seconds >= self.auto_save_interval:
                self._auto_save()
            
            self._notify_callbacks()
    
    def complete_step(self, step_name: str):
        """Termine une étape"""
        with self._lock:
            if step_name not in self.steps:
                return
            
            step = self.steps[step_name]
            step.complete()
            
            print(f"✅ Étape terminée: {step_name} ({step.duration})")
            self._notify_callbacks()
    
    def fail_step(self, step_name: str, error_message: str = None):
        """Marque une étape comme échouée"""
        with self._lock:
            if step_name not in self.steps:
                return
            
            step = self.steps[step_name]
            step.fail(error_message)
            self.failed_operations += 1
            
            print(f"❌ Étape échouée: {step_name}")
            if error_message:
                print(f"   Erreur: {error_message}")
            
            self._notify_callbacks()
    
    def add_step_error(self, step_name: str, error_message: str):
        """Ajoute une erreur à une étape sans la faire échouer"""
        with self._lock:
            if step_name not in self.steps:
                return
            
            step = self.steps[step_name]
            step.add_error(error_message)
            print(f"⚠️ Erreur dans {step_name}: {error_message}")
            self._notify_callbacks()
    
    def complete_operation(self):
        """Termine l'opération globale"""
        with self._lock:
            # Terminer l'étape courante si nécessaire
            if self.current_step:
                current = self.steps[self.current_step]
                if current.status == ProgressStatus.RUNNING:
                    current.complete()
            
            self.status = ProgressStatus.COMPLETED
            self.end_time = datetime.now()
            self._calculate_final_metrics()
            
            duration = self.end_time - self.start_time if self.start_time else None
            print(f"🎉 Opération terminée: {self.operation_name} ({duration})")
            print(f"📊 Taux de succès: {self.success_rate:.1f}%")
            
            self._notify_callbacks()
    
    def fail_operation(self, error_message: str = None):
        """Marque l'opération comme échouée"""
        with self._lock:
            self.status = ProgressStatus.FAILED
            self.end_time = datetime.now()
            
            if error_message:
                if self.current_step:
                    self.add_step_error(self.current_step, error_message)
            
            print(f"💥 Opération échouée: {self.operation_name}")
            if error_message:
                print(f"   Erreur: {error_message}")
            
            self._notify_callbacks()
    
    def pause_operation(self):
        """Met en pause l'opération"""
        with self._lock:
            self.status = ProgressStatus.PAUSED
            print(f"⏸️ Opération mise en pause: {self.operation_name}")
            self._notify_callbacks()
    
    def resume_operation(self):
        """Reprend l'opération"""
        with self._lock:
            self.status = ProgressStatus.RUNNING
            print(f"▶️ Reprise de l'opération: {self.operation_name}")
            self._notify_callbacks()
    
    def cancel_operation(self):
        """Annule l'opération"""
        with self._lock:
            self.status = ProgressStatus.CANCELLED
            self.end_time = datetime.now()
            print(f"🚫 Opération annulée: {self.operation_name}")
            self._notify_callbacks()
    
    def get_overall_progress(self) -> float:
        """Calcule la progression globale"""
        if not self.steps:
            return 0.0
        
        total_weight = len(self.steps)
        completed_weight = 0
        
        for step in self.steps.values():
            if step.status == ProgressStatus.COMPLETED:
                completed_weight += 1
            elif step.status == ProgressStatus.RUNNING:
                completed_weight += step.progress_percentage / 100
        
        return (completed_weight / total_weight) * 100
    
    def get_estimated_time_remaining(self) -> Optional[timedelta]:
        """Estime le temps restant total"""
        if not self.start_time or self.status != ProgressStatus.RUNNING:
            return None
        
        overall_progress = self.get_overall_progress()
        if overall_progress == 0:
            return None
        
        elapsed = datetime.now() - self.start_time
        total_estimated = elapsed.total_seconds() * (100 / overall_progress)
        remaining = total_estimated - elapsed.total_seconds()
        
        return timedelta(seconds=max(0, remaining))
    
    def get_current_step_info(self) -> Optional[Dict[str, Any]]:
        """Retourne les informations de l'étape courante"""
        if not self.current_step or self.current_step not in self.steps:
            return None
        
        step = self.steps[self.current_step]
        return {
            'name': step.name,
            'description': step.description,
            'progress': step.progress_percentage,
            'completed': step.completed_items,
            'total': step.total_items,
            'status': step.status.value,
            'duration': str(step.duration) if step.duration else None,
            'eta': str(step.estimated_time_remaining) if step.estimated_time_remaining else None,
            'errors': step.errors
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Retourne un résumé complet de la progression"""
        return {
            'session_id': self.session_id,
            'operation_name': self.operation_name,
            'status': self.status.value,
            'overall_progress': self.get_overall_progress(),
            'current_step': self.get_current_step_info(),
            'steps': {
                name: {
                    'description': step.description,
                    'progress': step.progress_percentage,
                    'status': step.status.value,
                    'completed': step.completed_items,
                    'total': step.total_items,
                    'errors_count': len(step.errors),
                    'duration': str(step.duration) if step.duration else None
                }
                for name, step in self.steps.items()
            },
            'metrics': {
                'total_operations': self.total_operations,
                'completed_operations': self.completed_operations,
                'failed_operations': self.failed_operations,
                'success_rate': self.success_rate
            },
            'timing': {
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'end_time': self.end_time.isoformat() if self.end_time else None,
                'duration': str(self.end_time - self.start_time) if self.start_time and self.end_time else None,
                'eta': str(self.get_estimated_time_remaining()) if self.get_estimated_time_remaining() else None
            }
        }
    
    def add_callback(self, callback: Callable):
        """Ajoute un callback appelé à chaque mise à jour"""
        self.update_callbacks.append(callback)
    
    def remove_callback(self, callback: Callable):
        """Supprime un callback"""
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)
    
    def _notify_callbacks(self):
        """Notifie tous les callbacks"""
        for callback in self.update_callbacks:
            try:
                callback(self.get_summary())
            except Exception as e:
                print(f"❌ Erreur callback: {e}")
    
    def _calculate_final_metrics(self):
        """Calcule les métriques finales"""
        completed_steps = sum(1 for step in self.steps.values() if step.status == ProgressStatus.COMPLETED)
        failed_steps = sum(1 for step in self.steps.values() if step.status == ProgressStatus.FAILED)
        total_steps = len(self.steps)
        
        if total_steps > 0:
            self.success_rate = (completed_steps / total_steps) * 100
        
        # Compter les opérations dans les métadonnées des étapes
        self.total_operations = sum(step.total_items for step in self.steps.values())
        self.completed_operations = sum(step.completed_items for step in self.steps.values())
        self.failed_operations = sum(len(step.errors) for step in self.steps.values())
    
    def _auto_save(self):
        """Sauvegarde automatique périodique"""
        try:
            # Ici on pourrait sauvegarder en base ou fichier
            # Pour l'instant, juste marquer la dernière sauvegarde
            self._last_save = datetime.now()
            print(f"💾 Auto-save: {self.operation_name}")
        except Exception as e:
            print(f"❌ Erreur auto-save: {e}")
    
    def print_progress_bar(self, step_name: Optional[str] = None):
        """Affiche une barre de progression dans la console"""
        if step_name and step_name in self.steps:
            step = self.steps[step_name]
            progress = step.progress_percentage
            title = f"{step_name}: {step.description}"
        else:
            progress = self.get_overall_progress()
            title = f"{self.operation_name} (Global)"
        
        # Créer la barre
        bar_length = 50
        filled_length = int(bar_length * progress / 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        # Informations additionnelles
        eta = self.get_estimated_time_remaining()
        eta_str = f" | ETA: {eta}" if eta else ""
        
        print(f"\r{title}: |{bar}| {progress:.1f}%{eta_str}", end='', flush=True)
        
        if progress >= 100:
            print()  # Nouvelle ligne quand terminé


class SimpleProgressTracker:
    """Version simplifiée du tracker pour des opérations basiques"""
    
    def __init__(self, total_items: int, description: str = "Processing"):
        self.total_items = total_items
        self.completed_items = 0
        self.description = description
        self.start_time = datetime.now()
        self.last_update = self.start_time
        
    def update(self, completed: int = None):
        """Met à jour la progression"""
        if completed is not None:
            self.completed_items = completed
        else:
            self.completed_items += 1
        
        # Afficher la progression toutes les secondes
        now = datetime.now()
        if (now - self.last_update).seconds >= 1 or self.completed_items >= self.total_items:
            self._print_progress()
            self.last_update = now
    
    def _print_progress(self):
        """Affiche la progression simple"""
        progress = (self.completed_items / self.total_items) * 100 if self.total_items > 0 else 0
        
        # Estimation du temps restant
        elapsed = datetime.now() - self.start_time
        if self.completed_items > 0:
            rate = self.completed_items / elapsed.total_seconds()
            remaining = (self.total_items - self.completed_items) / rate if rate > 0 else 0
            eta_str = f" | ETA: {timedelta(seconds=int(remaining))}"
        else:
            eta_str = ""
        
        # Barre de progression
        bar_length = 30
        filled = int(bar_length * progress / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        print(f"\r{self.description}: |{bar}| {self.completed_items}/{self.total_items} ({progress:.1f}%){eta_str}", 
              end='', flush=True)
        
        if self.completed_items >= self.total_items:
            duration = datetime.now() - self.start_time
            print(f"\n✅ Terminé en {duration}")


# Fonction utilitaire pour créer rapidement un tracker simple
def create_simple_tracker(total_items: int, description: str = "Processing") -> SimpleProgressTracker:
    """Crée un tracker simple pour des opérations basiques"""
    return SimpleProgressTracker(total_items, description)