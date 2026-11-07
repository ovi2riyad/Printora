# Matching-bitness isolated TWAIN 1.x system DSM adapter; no vendor DLL is loaded in Qt.
$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
try {
    if ([IntPtr]::Size -ne 4) { throw 'The installed legacy TWAIN adapter requires 32-bit Windows PowerShell' }
    $windows=[Environment]::GetFolderPath('Windows')
    $dll=Join-Path $windows 'twain_32.dll'
    if (-not (Test-Path -LiteralPath $dll)) {$dll=Join-Path $windows 'SysWOW64\twain_32.dll'}
    if (-not (Test-Path -LiteralPath $dll)) { throw 'No system 32-bit TWAIN DSM is installed' }
    $pe=[System.IO.File]::ReadAllBytes($dll);$peOffset=[BitConverter]::ToInt32($pe,60)
    if ([BitConverter]::ToUInt16($pe,$peOffset+4) -ne 0x14c) {throw 'Installed DSM does not match this 32-bit helper'}
    Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition (@'
using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using System.Threading;
public class PrintoraTwain {
 [StructLayout(LayoutKind.Sequential,Pack=2,CharSet=CharSet.Ansi)] public struct Version {
  public ushort Major,Minor,Language,Country; [MarshalAs(UnmanagedType.ByValTStr,SizeConst=34)] public string Info;
 }
 [StructLayout(LayoutKind.Sequential,Pack=2,CharSet=CharSet.Ansi)] public struct Identity {
  public uint Id; public Version Version;public ushort ProtocolMajor,ProtocolMinor;public uint Groups;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=34)] public string Manufacturer;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=34)] public string Family;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=34)] public string Name;
 }
 [StructLayout(LayoutKind.Sequential,Pack=2)] struct Capability {public ushort Cap,Container;public IntPtr Handle;}
 [StructLayout(LayoutKind.Sequential,Pack=2)] struct UserInterface {public ushort Show,Modal;public IntPtr Parent;}
 [StructLayout(LayoutKind.Sequential,Pack=2)] struct TwainEvent {public IntPtr Message;public ushort Kind;}
 [StructLayout(LayoutKind.Sequential)] struct WinMessage {public IntPtr Hwnd;public uint Msg;public IntPtr WParam,LParam;public uint Time;public int X,Y;}
 [DllImport(@"__DSM__",EntryPoint="DSM_Entry",CallingConvention=CallingConvention.StdCall)]
 static extern ushort Entry(ref Identity app,IntPtr dest,uint dg,ushort dat,ushort msg,IntPtr data);
 [DllImport("kernel32.dll")] static extern IntPtr GlobalAlloc(uint flags,UIntPtr size);
 [DllImport("kernel32.dll")] static extern IntPtr GlobalLock(IntPtr h);
 [DllImport("kernel32.dll")] static extern bool GlobalUnlock(IntPtr h);
 [DllImport("kernel32.dll")] static extern IntPtr GlobalFree(IntPtr h);
 [DllImport("kernel32.dll")] static extern UIntPtr GlobalSize(IntPtr h);
 [DllImport("user32.dll")] static extern bool PeekMessage(out WinMessage msg,IntPtr hwnd,uint min,uint max,uint remove);
 [DllImport("user32.dll")] static extern bool TranslateMessage(ref WinMessage msg);
 [DllImport("user32.dll")] static extern IntPtr DispatchMessage(ref WinMessage msg);
 Identity app;IntPtr source=IntPtr.Zero;Form window;IntPtr parent;bool opened=false,enabled=false;
 public List<string> Diagnostics=new List<string>();
 public PrintoraTwain() {
  if(Marshal.SizeOf(typeof(Identity))!=156)throw new Exception("Invalid TWAIN structure packing");
  app=new Identity {Version=new Version {Major=1,Minor=0,Info="Printora isolated bridge"},ProtocolMajor=1,ProtocolMinor=9,Groups=3,Manufacturer="Printora",Family="Document studio",Name="Printora"};
  window=new Form();parent=Marshal.AllocHGlobal(IntPtr.Size);Marshal.WriteIntPtr(parent,window.Handle);
  if(Entry(ref app,IntPtr.Zero,1,4,0x301,parent)!=0)throw new Exception("TWAIN DSM could not open");opened=true;
 }
 ushort Call(uint dg,ushort dat,ushort msg,IntPtr data){return Entry(ref app,source,dg,dat,msg,data);}
 public List<Identity> Devices(){
  var list=new List<Identity>();IntPtr p=Marshal.AllocHGlobal(156);
  try {ushort result=Entry(ref app,IntPtr.Zero,1,3,4,p);while(result==0 && list.Count<100){list.Add((Identity)Marshal.PtrToStructure(p,typeof(Identity)));result=Entry(ref app,IntPtr.Zero,1,3,5,p);}}finally{Marshal.FreeHGlobal(p);}return list;
 }
 public void Open(string name){
  Identity? chosen=null;foreach(var id in Devices())if(id.Name==name){chosen=id;break;}
  if(!chosen.HasValue)throw new Exception("TWAIN source not found; refresh devices");
  source=Marshal.AllocHGlobal(156);Marshal.StructureToPtr(chosen.Value,source,false);
  if(Entry(ref app,IntPtr.Zero,1,3,0x401,source)!=0){Marshal.FreeHGlobal(source);source=IntPtr.Zero;throw new Exception("TWAIN driver could not open; check connection or another application");}
 }
 static double ReadItem(IntPtr p,int offset,ushort type){
  if(type==7){uint v=(uint)Marshal.ReadInt32(p,offset);return (short)(v&65535)+((v>>16)&65535)/65536.0;}
  if(type==4 || type==6)return (ushort)Marshal.ReadInt16(p,offset);
  return Marshal.ReadInt32(p,offset);
 }
 public double[] Values(ushort id,ushort message){
  var cap=new Capability {Cap=id,Container=65535};IntPtr p=Marshal.AllocHGlobal(Marshal.SizeOf(cap));var values=new List<double>();
  try{
   Marshal.StructureToPtr(cap,p,false);ushort returned=Call(1,1,message,p);cap=(Capability)Marshal.PtrToStructure(p,typeof(Capability));Diagnostics.Add(id+"/"+message+":return="+returned+",container="+cap.Container);
   if((returned!=0 && returned!=2) || cap.Handle==IntPtr.Zero)return values.ToArray();
   IntPtr data=GlobalLock(cap.Handle);if(data==IntPtr.Zero)return values.ToArray();
   try {ushort type=(ushort)Marshal.ReadInt16(data);int stride=(type==4 || type==6)?2:4;
    if(cap.Container==5)values.Add(ReadItem(data,2,type));
    else if(cap.Container==4){int count=Marshal.ReadInt32(data,2);if(count>10000)throw new Exception("Driver returned excessive capability values");for(int i=0;i<count;i++)values.Add(ReadItem(data,14+i*stride,type));}
    else if(cap.Container==6){double min=ReadItem(data,2,type),max=ReadItem(data,6,type),step=ReadItem(data,10,type);foreach(double n in new double[]{75,100,150,200,300,400,600,1200,2400,4800,9600})if(n>=min && n<=max && (step==0 || Math.Abs((n-min)/step-Math.Round((n-min)/step))<.001))values.Add(n);}
   }finally{GlobalUnlock(cap.Handle);}
  }finally{if(cap.Handle!=IntPtr.Zero)GlobalFree(cap.Handle);Marshal.FreeHGlobal(p);}return values.ToArray();
 }
 public void Set(ushort id,ushort type,double value){
  IntPtr memory=GlobalAlloc(0x42,(UIntPtr)6);IntPtr data=GlobalLock(memory);Marshal.WriteInt16(data,(short)type);
  uint raw=type==7?((uint)(ushort)(short)value | ((uint)(ushort)((value-Math.Floor(value))*65536)<<16)):(uint)value;
  Marshal.WriteInt32(data,2,(int)raw);GlobalUnlock(memory);
  Capability cap=new Capability {Cap=id,Container=5,Handle=memory};IntPtr p=Marshal.AllocHGlobal(Marshal.SizeOf(cap));
  try{Marshal.StructureToPtr(cap,p,false);if(Call(1,1,6,p)!=0)throw new Exception("TWAIN driver refused setting "+id);
      var actual=Values(id,2);if(actual.Length!=1 || Math.Abs(actual[0]-value)>.01)throw new Exception("TWAIN driver changed requested setting "+id);
  }finally{Marshal.FreeHGlobal(p);GlobalFree(memory);}
 }
 public double[] DefaultFrame(){
  IntPtr p=Marshal.AllocHGlobal(28);try{
   for(int i=0;i<28;i++)Marshal.WriteByte(p,i,0);
   if(Call(2,0x102,3,p)!=0)throw new Exception("Driver did not expose default acquisition bounds");
   return new double[]{ReadItem(p,0,7),ReadItem(p,4,7),ReadItem(p,8,7),ReadItem(p,12,7)};
  }finally{Marshal.FreeHGlobal(p);}
 }
 public string Scan(string folder,string cancel,int dpi,string color,double[] region){
  Set(0x102,4,0);Set(0x1118,7,dpi);Set(0x1119,7,dpi);Set(0x101,4,color=="gray"?1:2);Set(0x103,4,0);
  IntPtr frame=Marshal.AllocHGlobal(28);
  try {for(int i=0;i<28;i++)Marshal.WriteByte(frame,i,0);double[] coords={region[0]/25.4,region[1]/25.4,(region[0]+region[2])/25.4,(region[1]+region[3])/25.4};
   for(int i=0;i<4;i++){double v=coords[i];Marshal.WriteInt16(frame,i*4,(short)Math.Floor(v));Marshal.WriteInt16(frame,i*4+2,(short)(ushort)((v-Math.Floor(v))*65536));}
   if(Call(2,0x102,6,frame)!=0)throw new Exception("TWAIN driver refused the acquisition region");
  }finally{Marshal.FreeHGlobal(frame);}
  if(File.Exists(cancel))throw new Exception("Canceled before acquisition");
  File.WriteAllText(Path.Combine(folder,"acquisition.started"),"TWAIN enable requested; outcome unknown");
  var ui=new UserInterface {Show=0,Modal=0,Parent=window.Handle};IntPtr u=Marshal.AllocHGlobal(Marshal.SizeOf(ui));Marshal.StructureToPtr(ui,u,false);
  try{if(Call(1,9,0x502,u)!=0)throw new Exception("TWAIN driver refused acquisition without its UI");enabled=true;
   DateTime deadline=DateTime.UtcNow.AddSeconds(210);IntPtr wm=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(WinMessage)));IntPtr ev=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(TwainEvent)));
   try{bool ready=false;while(DateTime.UtcNow<deadline && !ready){if(File.Exists(cancel))throw new Exception("Cancel requested; no completed transfer available");
    WinMessage msg;while(PeekMessage(out msg,IntPtr.Zero,0,0,1)){
     Marshal.StructureToPtr(msg,wm,false);Marshal.StructureToPtr(new TwainEvent {Message=wm},ev,false);
     ushort r=Call(1,2,0x601,ev);var te=(TwainEvent)Marshal.PtrToStructure(ev,typeof(TwainEvent));
     if(r==4 && te.Kind==0x101){ready=true;break;}if(r==4 && te.Kind==0x102)throw new Exception("Driver canceled acquisition");
     if(r!=4){TranslateMessage(ref msg);DispatchMessage(ref msg);}
    }Thread.Sleep(10);
   }if(!ready)throw new Exception("TWAIN acquisition timed out; do not retry until checking the device");
   }finally{Marshal.FreeHGlobal(wm);Marshal.FreeHGlobal(ev);}
   IntPtr transfer=Marshal.AllocHGlobal(IntPtr.Size);Marshal.WriteIntPtr(transfer,IntPtr.Zero);
   try{if(Call(2,0x104,1,transfer)!=6)throw new Exception("TWAIN transfer failed; outcome unknown");IntPtr handle=Marshal.ReadIntPtr(transfer);IntPtr dib=GlobalLock(handle);
    try{long length=(long)GlobalSize(handle).ToUInt64();if(length<40 || length>320000000)throw new Exception("Native bitmap exceeds transfer safety limit");
     int header=Marshal.ReadInt32(dib),width=Marshal.ReadInt32(dib,4),height=Math.Abs(Marshal.ReadInt32(dib,8));
     if(width<=0 || (long)width*height>80000000)throw new Exception("Bitmap exceeds 80 megapixels");
     int bits=(ushort)Marshal.ReadInt16(dib,14),compression=Marshal.ReadInt32(dib,16),colors=Marshal.ReadInt32(dib,32);
     int palette=colors>0?colors:(bits<=8?1<<bits:0);long offset=14L+header+palette*4L+((header==40 && compression==3)?12:0);
     if(header<40 || offset>length+14)throw new Exception("Unsupported native bitmap header");byte[] bytes=new byte[(int)length];Marshal.Copy(dib,bytes,0,bytes.Length);
     string path=Path.Combine(folder,"original.bmp");using(var file=new BinaryWriter(new FileStream(path,FileMode.CreateNew,FileAccess.Write))){file.Write((ushort)0x4d42);file.Write((uint)(length+14));file.Write((uint)0);file.Write((uint)offset);file.Write(bytes);file.Flush();}
     IntPtr pending=Marshal.AllocHGlobal(6);try{Call(1,5,0x701,pending);Call(1,5,7,pending);}finally{Marshal.FreeHGlobal(pending);}return path;
    }finally{GlobalUnlock(handle);GlobalFree(handle);}
   }finally{Marshal.FreeHGlobal(transfer);}
  }finally{if(enabled){Call(1,9,0x501,u);enabled=false;}Marshal.FreeHGlobal(u);}
 }
 public void Close(){if(source!=IntPtr.Zero){Entry(ref app,IntPtr.Zero,1,3,0x402,source);Marshal.FreeHGlobal(source);source=IntPtr.Zero;}if(opened){Entry(ref app,IntPtr.Zero,1,4,0x302,parent);opened=false;}if(parent!=IntPtr.Zero)Marshal.FreeHGlobal(parent);if(window!=null)window.Dispose();}
}
'@).Replace('__DSM__',$dll.Replace('"','""'))
    $request=[Console]::In.ReadLine() | ConvertFrom-Json
    $adapter=New-Object PrintoraTwain
    try {
        if ($request.action -eq 'devices') {
            $devices=@();foreach($device in $adapter.Devices()){$devices+=@{id=('twain32:'+$device.Name);name=($device.Name+' (TWAIN 32-bit)');backend='twain32';status='Installed source; acquisition not verified'}}
            $result=@{devices=$devices;bitness=32}
        } else {
            $name=([string]$request.device).Substring(8);$adapter.Open($name)
            if ($request.action -eq 'capabilities') {
                $x=@($adapter.Values(0x1118,1));$y=@($adapter.Values(0x1119,1));$dpi=@($x | Where-Object {$y -contains $_} | ForEach-Object {[int]$_} | Sort-Object -Unique)
                $types=@($adapter.Values(0x101,1));$colors=@();if($types -contains 2){$colors+='color'};if($types -contains 1){$colors+='gray'}
                $width=@($adapter.Values(0x1111,2));$height=@($adapter.Values(0x1112,2))
                $units=@($adapter.Values(0x102,2));$factor=25.4
                if ($units.Count -ne 1) {throw 'Driver did not expose physical units'}
                switch ([int]$units[0]) {0 {$factor=25.4} 1 {$factor=10} 2 {$factor=25.4/6} 3 {$factor=25.4/72} 4 {$factor=25.4/1440} default {throw 'Driver bounds use unsupported nonphysical units'}}
                $bounds='physical capabilities'
                if ($width.Count -eq 1 -and $height.Count -eq 1 -and ($width[0] -le 0 -or $height[0] -le 0)) {
                    $frame=@($adapter.DefaultFrame())
                    if ($frame[0] -ne 0 -or $frame[1] -ne 0) {throw 'Nonzero default bounds need explicit driver calibration'}
                    $width=@($frame[2]);$height=@($frame[3]);$bounds='driver default frame'
                }
                if (-not $width -or -not $height -or -not $dpi) {throw ('TWAIN driver did not report safe physical bounds/resolutions. X='+($x -join ',')+' Y='+($y -join ',')+' Width='+($width -join ',')+' Height='+($height -join ',')+' '+($adapter.Diagnostics -join '; '))}
                $result=@{sources=@(@{id='default';name='Driver default scan source';resolutions=@($dpi|Where-Object {$_ -ge 50 -and $_ -le 9600});colors=$colors;width_mm=($width[0]*$factor);height_mm=($height[0]*$factor);formats=@('native BMP');bounds=$bounds});status='Connected through isolated 32-bit TWAIN; acquisition unverified'}
            } elseif ($request.action -eq 'scan') {
                $path=$adapter.Scan($request.folder,$request.cancel,[int]$request.dpi,$request.color,[double[]]$request.region)
                $result=@{path=$path;dpi=[int]$request.dpi;acquired=$true;canceled=(Test-Path -LiteralPath $request.cancel);format='native BMP';backend='twain32'}
            } else {throw 'Unsupported TWAIN request'}
        }
    } finally {$adapter.Close()}
    [Console]::WriteLine((@{ok=$true;result=$result}|ConvertTo-Json -Depth 9 -Compress))
} catch {[Console]::WriteLine((@{ok=$false;error=$_.Exception.Message}|ConvertTo-Json -Compress));exit 1}
