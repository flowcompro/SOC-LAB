$ServiceName = 'appreadiness' 
$arrService = Get-Service -Name $ServiceName -ComputerName ftp

while ($arrService.Status -ne 'Running')
{

    Get-Service -Name $ServiceName -ComputerName ftp | Set-Service -Status Running
    write-host $ServiceName $arrService.status
    write-host $ServiceName 'Service starting'
    Start-Sleep -seconds 5
    $arrService.Refresh()
    if ($arrService.Status -eq 'Running')
    {
        Write-Host  $ServiceName 'Service is now Running'
    }

}

$ServiceName = 'BITS' 
$arrService = Get-Service -Name $ServiceName -ComputerName ftp

while ($arrService.Status -ne 'Running')
{

    Get-Service -Name $ServiceName -ComputerName ftp | Set-Service -Status Running
    write-host $ServiceName $arrService.status
    write-host $ServiceName 'Service starting'
    Start-Sleep -seconds 5
    $arrService.Refresh()
    if ($arrService.Status -eq 'Running')
    {
        Write-Host  $ServiceName 'Service is now Running'
    }

}

$ServiceName = 'iphlpsvc' 
$arrService = Get-Service -Name $ServiceName -ComputerName ftp

while ($arrService.Status -ne 'Running')
{

    Get-Service -Name $ServiceName -ComputerName ftp | Set-Service -Status Running
    write-host $ServiceName $arrService.status
    write-host $ServiceName 'Service starting'
    Start-Sleep -seconds 5
    $arrService.Refresh()
    if ($arrService.Status -eq 'Running')
    {
        Write-Host  $ServiceName 'Service is now Running'
    }

}

$ServiceName = 'SysMain' 
$arrService = Get-Service -Name $ServiceName -ComputerName ftp

while ($arrService.Status -ne 'Running')
{

    Get-Service -Name $ServiceName -ComputerName ftp | Set-Service -Status Running
    write-host $ServiceName $arrService.status
    write-host $ServiceName 'Service starting'
    Start-Sleep -seconds 5
    $arrService.Refresh()
    if ($arrService.Status -eq 'Running')
    {
        Write-Host  $ServiceName 'Service is now Running'
    }

}

Write-Host 'Script is complete, you can close the windows now'
