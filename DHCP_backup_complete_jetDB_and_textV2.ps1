 # === GLOBAL CONFIGURATION ===
$DateStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$DateFolder = "DHCP Backup Dated $($DateStamp.Substring(0,8))"

# TEXT EXPORT DESTINATION
$TextRoot     = "\\fs\backups\DHCP\DHCP_TextBackups"
$TextFolder   = Join-Path -Path $TextRoot -ChildPath "DHCP_text_backup $DateStamp"
$TextLogFile  = Join-Path -Path $TextRoot -ChildPath "dhcp_backup_status.log"

# JET DB DESTINATION
$JetRoot          = "\\fs\backups\DHCP\DHCP_JetBackups"
$JetFolder        = Join-Path -Path $JetRoot -ChildPath "DHCP Jet Backup $DateStamp"
$JetLogFile       = Join-Path -Path $JetRoot -ChildPath "dhcp_jet_backup.log"
$JetSource        = "$env:SystemRoot\System32\dhcp\backup"

# === GENERAL LOG FUNCTION ===
function Write-Log {
    param (
        [string]$Message,
        [string]$LogPath
    )
    $Timestamped = "$(Get-Date -Format "s") - $Message"
    Write-Output $Timestamped
    try {
        Add-Content -Path $LogPath -Value $Timestamped
    } catch {
        Write-Warning "Could not write to log file: $_"
    }
}

# === TEXT EXPORT BACKUP ===
try {
    New-Item -Path $TextFolder -ItemType Directory -Force | Out-Null
    $ExportFile = Join-Path -Path $TextFolder -ChildPath "dhcp_backup_$DateStamp.txt"
    netsh dhcp server export "$ExportFile" all
    Write-Log "SUCCESS: DHCP text export saved to $ExportFile" $TextLogFile
} catch {
    Write-Log "ERROR during text export: $($_.Exception.Message)" $TextLogFile
}

# === JET DB BACKUP ===
try {
    Write-Log "Starting DHCP Jet database backup..." $JetLogFile

    # Ensure destination exists
    if (!(Test-Path $JetFolder)) {
        New-Item -Path $JetFolder -ItemType Directory -Force | Out-Null
    }

    # Stop DHCP Server for clean backup
    Write-Log "Stopping DHCP Server service..." $JetLogFile
    Stop-Service dhcpserver -Force -ErrorAction Stop

    # Copy the Jet database backup folder
    Write-Log "Copying backup from $JetSource to $JetFolder..." $JetLogFile
    Copy-Item -Path "$JetSource\*" -Destination $JetFolder -Recurse -Force -ErrorAction Stop

    # Start DHCP Server again
    Write-Log "Starting DHCP Server service..." $JetLogFile
    Start-Service dhcpserver -ErrorAction Stop

    Write-Log "SUCCESS: Jet database backup completed to $JetFolder" $JetLogFile
} catch {
    Write-Log "ERROR: Jet DB backup failed - $($_.Exception.Message)" $JetLogFile
}

# === FINAL STATUS LOG ===
Write-Log "COMPLETED: DHCP backup finished for $DateStamp" $TextLogFile
Exit 0
