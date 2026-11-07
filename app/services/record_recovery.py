"""GUI record-load boundaries; damaged records remain available for recovery."""
from functools import wraps
from pathlib import Path

def checked_document(job):
    if not isinstance(job.photos,list):raise ValueError('Invalid photograph list')
    for photo in job.photos:
        photo.validate()
        for layer in photo.layers:
            if not isinstance(layer.source,str) or not layer.source:raise ValueError('Required original image path is missing')
            for path in (layer.source,layer.mask):
                if path and not Path(path).is_file():raise ValueError('A required source or mask is missing. Restore it from a backup.')
    return job

def recoverable_record(function):
    @wraps(function)
    def guarded(self,*args,**kwargs):
        try:return function(self,*args,**kwargs)
        except (ValueError,TypeError,KeyError,AttributeError,OSError,OverflowError,RecursionError) as error:
            from PySide6.QtWidgets import QMessageBox,QWidget
            owner=self if isinstance(self,QWidget) else self.w
            if hasattr(self,'loading'):self.loading=False
            identity=str(args[0]) if args and isinstance(args[0],str) else getattr(self,'current_id',None) or 'selected record'
            QMessageBox.warning(owner,'Record could not be opened',f'Record: {identity}\n{type(error).__name__}: {error}\nThe stored record was retained. Restore missing assets or recover this record from a verified backup.')
            return None
    return guarded
