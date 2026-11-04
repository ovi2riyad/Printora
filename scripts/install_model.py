"""One-time explicit model setup; photographs are never transmitted."""
import hashlib
import urllib.request
from app.core.database import Database,data_root

def main():
    db=Database();folder=data_root()/'models';folder.mkdir(parents=True,exist_ok=True)
    tmp=folder/'u2net_human_seg.download'
    try:
        urllib.request.urlretrieve('https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx',tmp)
        if hashlib.md5(tmp.read_bytes()).hexdigest()!='c09ddc2e0104f800e3e1bb4652583d1f':raise ValueError('Model checksum mismatch')
        tmp.replace(folder/'u2net_human_seg.onnx');db.set('model_dir',str(folder));print('Installed:',folder/'u2net_human_seg.onnx')
    finally:
        if tmp.exists():tmp.unlink()
        db.conn.close()

if __name__=='__main__':main()
