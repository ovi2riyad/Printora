"""User-facing working folders; internal databases/assets keep their existing home."""
from pathlib import Path
from PySide6.QtCore import QStandardPaths

KINDS={'input':'Input','output':'Output','scans':'Scans','backups':'Backups'}

def documents_directory():
    # Qt uses the Windows Known Folder API, including redirected/OneDrive Documents.
    value=QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return Path(value) if value else Path.home()/'Documents'

def defaults():
    root=documents_directory()/'Printora'
    return {('output' if kind=='output' else kind+'_folder'):str(root/name) for kind,name in KINDS.items()}

def folder(db,kind,create=True):
    if kind not in KINDS:raise ValueError('Unknown working folder: '+kind)
    key='output' if kind=='output' else kind+'_folder'
    path=Path(db.get(key,defaults()[key]) if db else defaults()[key]).expanduser()
    if not path.is_absolute():raise ValueError('Choose an absolute '+kind+' folder in Settings > Folders.')
    if create:
        try:path.mkdir(parents=True,exist_ok=True)
        except OSError as error:raise ValueError('Cannot open '+kind+' folder. Choose a writable folder in Settings > Folders.') from error
    return path

def output_path(db,name,kind='output'):
    # A document name cannot escape the selected working folder.
    safe=str(name).replace('\\','-').replace('/','-').replace(':','-')
    return str(folder(db,kind)/safe)

def dialog_folder(db,kind,notify=lambda text:None):
    """A bad/unwritable preference must not escape a Qt button callback."""
    try:return str(folder(db,kind))
    except ValueError as error:
        notify(str(error));return ''

def dialog_output(db,name,notify=lambda text:None,kind='output'):
    directory=dialog_folder(db,kind,notify)
    if not directory:return ''
    safe=str(name).replace('\\','-').replace('/','-').replace(':','-')
    return str(Path(directory)/safe)
