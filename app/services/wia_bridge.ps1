# Windows WIA Automation is apartment threaded. Run with Windows PowerShell -STA.
# One request per process: a stalled vendor driver never runs in the Qt GUI.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Find-Property($object, [int]$id) {
    foreach ($property in $object.Properties) { if ($property.PropertyID -eq $id) { return $property } }
    return $null
}
function Set-Property($object, [int]$id, $value) {
    $property = Find-Property $object $id
    if ($null -eq $property) { throw "Driver does not expose WIA property $id" }
    $property.Value = $value
    if ([double]$property.Value -ne [double]$value) { throw "Driver changed requested WIA property $id" }
}
function Get-Values($property) {
    if ($null -eq $property) { return @() }
    if ($property.SubType -eq 2 -or $property.SubType -eq 3) { return @($property.SubTypeValues | ForEach-Object { [int]$_ }) }
    if ($property.SubType -eq 1) {
        $values = @()
        # Bound huge ranges; common photographic choices still require exact range/step validation.
        foreach ($n in @(75,100,150,200,300,400,600,1200,2400,4800,9600,[int]$property.Value)) {
            if ($n -ge $property.SubTypeMin -and $n -le $property.SubTypeMax -and
                (($n - $property.SubTypeMin) % [Math]::Max(1,$property.SubTypeStep)) -eq 0) { $values += $n }
        }
        return @($values | Sort-Object -Unique)
    }
    return @([int]$property.Value)
}
function All-Items($items) {
    foreach ($entry in $items) {
        if ($null -ne (Find-Property $entry 6147)) { $entry }
        if ($entry.Items.Count -gt 0) { All-Items $entry.Items }
    }
}
try {
    $request = [Console]::In.ReadLine() | ConvertFrom-Json
    $manager = New-Object -ComObject WIA.DeviceManager
    if ($request.action -eq 'devices') {
        $devices = @()
        foreach ($info in $manager.DeviceInfos) {
            if ($info.Type -eq 1) {
                $name = ($info.Properties | Where-Object { $_.PropertyID -eq 7 } | Select-Object -First 1).Value
                $devices += @{id=$info.DeviceID;name=[string]$name;backend='wia';status='Detected; connect to check availability'}
            }
        }
        $result = @{devices=$devices}
    } else {
        $info = $manager.DeviceInfos | Where-Object { $_.DeviceID -eq $request.device } | Select-Object -First 1
        if ($null -eq $info) { throw 'Scanner not found. Reconnect it and refresh devices.' }
        $device = $info.Connect()
        $items = @(All-Items $device.Items)
        $item = $items | Where-Object { $_.ItemID -eq $request.item } | Select-Object -First 1
        if ($request.action -eq 'capabilities') {
            $sources = @()
            foreach ($entry in $items) {
                $xp = Find-Property $entry 6147; $yp = Find-Property $entry 6148
                $yvalues = @(Get-Values $yp)
                $resolutions = @(Get-Values $xp | Where-Object { $yvalues -contains $_ } | Sort-Object -Unique)
                $types = @(Get-Values (Find-Property $entry 4103)); $colors = @()
                if ($types -contains 3) { $colors += 'color' }; if ($types -contains 2) { $colors += 'gray' }
                $width = (Find-Property $entry 6151).SubTypeMax / [double]$xp.Value * 25.4
                $height = (Find-Property $entry 6152).SubTypeMax / [double]$yp.Value * 25.4
                $category=Find-Property $entry 4125
                $feeder=($null -ne $category -and ([string]$category.Value).Trim('{}') -eq 'fe131934-f84c-42ad-8da4-6129cddd7288')
                $pages=Find-Property $entry 3096
                $batch=($feeder -and $null -ne $pages -and $null -ne (Find-Property $entry 3088))
                $sources += @{id=$entry.ItemID;name=[string](Find-Property $entry 4098).Value;
                    resolutions=$resolutions;colors=$colors;width_mm=$width;height_mm=$height;formats=@($entry.Formats);feeder=$feeder;batch=$batch}
            }
            if ($sources.Count -eq 0) { throw 'No WIA acquisition item is exposed by this driver' }
            $result = @{sources=$sources;status='Ready (WIA connection succeeded)'}
        } elseif ($request.action -eq 'scan') {
            if ($null -eq $item) { throw 'Selected scan source is no longer available' }
            if (Test-Path -LiteralPath $request.cancel) { throw 'Canceled before acquisition' }
            $count=1
            if ($null -ne $request.max_pages) {$count=[int]$request.max_pages}
            if ($count -lt 1 -or $count -gt 100) {throw 'Choose 1 to 100 feeder pages'}
            $category=Find-Property $item 4125
            $feeder=($null -ne $category -and ([string]$category.Value).Trim('{}') -eq 'fe131934-f84c-42ad-8da4-6129cddd7288')
            if ($count -gt 1 -and -not $feeder) {throw 'This source is not a driver-reported feeder'}
            if ($feeder) {
                # Require explicit single-sided, single-page transfers. A driver
                # that cannot honor either property fails BEFORE the first feed.
                Set-Property $item 3088 1
                Set-Property $item 3096 1
            }
            $intent = 1; $datatype = 3
            if ($request.color -eq 'gray') { $intent = 2; $datatype = 2 }
            Set-Property $item 6146 $intent
            Set-Property $item 4103 $datatype
            Set-Property $item 6147 ([int]$request.dpi)
            Set-Property $item 6148 ([int]$request.dpi)
            # Re-read limits AFTER changing resolution. Do not scale old pixel extents.
            Set-Property $item 6149 0; Set-Property $item 6150 0
            $maxw = [int](Find-Property $item 6151).SubTypeMax
            $maxh = [int](Find-Property $item 6152).SubTypeMax
            $x = [int][Math]::Round($request.region[0] * $request.dpi / 25.4)
            $y = [int][Math]::Round($request.region[1] * $request.dpi / 25.4)
            $w = [int][Math]::Round($request.region[2] * $request.dpi / 25.4)
            $h = [int][Math]::Round($request.region[3] * $request.dpi / 25.4)
            if ($x+$w -gt $maxw+1 -or $y+$h -gt $maxh+1) { throw 'Region exceeds current driver limits' }
            $w = [Math]::Min($w,$maxw-$x); $h = [Math]::Min($h,$maxh-$y)
            Set-Property $item 6151 $w; Set-Property $item 6152 $h
            Set-Property $item 6149 $x; Set-Property $item 6150 $y
            if ([long]$w*$h -gt 80000000) { throw 'Scan exceeds 80 megapixels' }
            $formats = @($item.Formats)
            $format = $null; $extension = $null
            # Only lossless driver-reported formats. No implicit JPEG conversion.
            foreach ($candidate in @(@('{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}','png'),
                                      @('{B96B3CB1-0728-11D3-9D7B-0000F81EF32E}','tif'),
                                      @('{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}','bmp'))) {
                if ($formats -contains $candidate[0]) { $format=$candidate[0];$extension=$candidate[1];break }
            }
            if ($null -eq $format) { throw 'Driver exposes no supported lossless transfer format (PNG/TIFF/BMP)' }
            $completed=@();$warning='';$partial=$false
            for ($index=0;$index -lt $count;$index++) {
                if (Test-Path -LiteralPath $request.cancel) {break}
                $folder=$request.folder
                if ($count -gt 1) {$folder=Join-Path $request.folder ('page-'+($index+1).ToString('D4'));[void][System.IO.Directory]::CreateDirectory($folder)}
                $path = Join-Path $folder ('original.'+$extension)
                if (Test-Path -LiteralPath $path) {throw 'Acquisition destination already exists'}
                [System.IO.File]::WriteAllText((Join-Path $request.folder 'acquisition.started'),'Transfer requested; outcome unknown until result')
                try {
                    if ($feeder) {Set-Property $item 3096 1}
                    $image=$item.Transfer($format);$image.SaveFile($path)
                    $completed+=@{path=$path;dpi=[int]$request.dpi;pixel_width=$image.Width;pixel_height=$image.Height;format=$format}
                } catch {
                    if ($completed.Count -eq 0) {throw}
                    $e=$_.Exception;while($null -ne $e.InnerException){$e=$e.InnerException}
                    if (($e.HResult -band 0xffffffffL) -eq 0x80210003L) {$warning='Feeder empty. Completed pages retained.'}
                    else {$partial=$true;$warning='Feeder stopped with a driver error. Review completed pages and the scanner; no retry was started.'}
                    break
                }
            }
            if ($completed.Count -eq 0) {throw 'Canceled before any page completed'}
            $result=@{path=$completed[0].path;dpi=[int]$request.dpi;acquired=$true;canceled=(Test-Path -LiteralPath $request.cancel);format=$format;partial=$partial;warning=$warning}
            if ($count -gt 1) {$result.pages=$completed;$result.limit_reached=($completed.Count -eq $count)}
        } else { throw 'Unknown scanner operation' }
    }
    [Console]::WriteLine((@{ok=$true;result=$result} | ConvertTo-Json -Depth 9 -Compress))
} catch {
    $exception = $_.Exception
    while ($null -ne $exception.InnerException) { $exception = $exception.InnerException }
    [Console]::WriteLine((@{ok=$false;error=$exception.Message;hresult=$exception.HResult} | ConvertTo-Json -Compress))
    exit 1
}
