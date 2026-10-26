# PC Price Tracker tray icon: countdown to the daily auto run, Run now, Autorun on/off (off = reminder only), Settings, latest report.
# Started at login by the "PC Price Tracker" shortcut in the Startup folder (Settings > Start with Windows).
# Reads run_time/autorun from settings.json (the Settings window writes it); keeps last_run/handled in state.json.
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$dir = $PSScriptRoot
$settingsFile = Join-Path $dir 'settings.json'
$stateFile = Join-Path $dir 'state.json'
$bat = Join-Path $dir 'run.bat'
$output = Join-Path $dir 'output'
$LATE_MINUTES = 10  # a slot missed by more than this (PC was off/asleep) reminds instead of starting a surprise scrape

$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'PCPriceTrackerTray', [ref]$created)
if (-not $created) { exit }  # already in the tray

function Read-Json($path) {
    $h = @{}
    try { (Get-Content $path -Raw -ErrorAction Stop | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $h[$_.Name] = $_.Value } } catch { }
    $h  # missing/unreadable file: empty, so defaults apply
}
function Write-Json($path, $h) { [IO.File]::WriteAllText($path, ($h | ConvertTo-Json -Depth 5)) }  # UTF-8 without BOM

$state = @{ autorun = $true; time = '12:00'; last_run = ''; handled = '' }  # handled = date today's slot was run or reminded
$saved = Read-Json $stateFile
foreach ($k in 'last_run', 'handled') { if ($saved[$k]) { $state[$k] = $saved[$k] } }
function Read-Settings {  # every tick, so a time saved in the Settings window counts within 20s
    $s = Read-Json $settingsFile
    $state.time = if ($s.run_time -match '^([01]?\d|2[0-3]):[0-5]\d$') { $s.run_time } else { '12:00' }
    $state.autorun = if ($null -eq $s.autorun) { $true } else { [bool]$s.autorun }
}
Read-Settings
function Save-State {  # merge: run.py writes the facebook result into the same file
    $h = Read-Json $stateFile
    $h.last_run = $state.last_run
    $h.handled = $state.handled
    Write-Json $stateFile $h
}

function Get-Today { (Get-Date).ToString('yyyy-MM-dd') }

function Get-Due {
    $at = [datetime]::ParseExact("$(Get-Today) $($state.time)", 'yyyy-MM-dd H:mm', $null)
    if ($state.handled -eq (Get-Today)) { $at = $at.AddDays(1) }
    $at
}

function Format-Left($span) {
    if ($span.TotalMinutes -lt 1) { return 'under 1m' }
    if ($span.TotalHours -ge 1) { return '{0}h {1:00}m' -f [int][math]::Floor($span.TotalHours), $span.Minutes }
    '{0}m' -f [int][math]::Ceiling($span.TotalMinutes)
}

function Test-Running { $script:proc -and -not $script:proc.HasExited }

# --- icon: blue circle with a peso sign ---
$bmp = New-Object System.Drawing.Bitmap 32, 32
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = 'AntiAlias'
$g.TextRenderingHint = 'AntiAliasGridFit'
$g.FillEllipse((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(30, 64, 175))), 0, 0, 31, 31)
$font = New-Object System.Drawing.Font('Segoe UI', 18, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$fmt = New-Object System.Drawing.StringFormat
$fmt.Alignment = 'Center'
$fmt.LineAlignment = 'Center'
$g.DrawString([string][char]0x20B1, $font, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF(0, 1, 32, 32)), $fmt)

$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
$icon.Visible = $true

# --- menu ---
$menu = New-Object System.Windows.Forms.ContextMenuStrip
$status = New-Object System.Windows.Forms.ToolStripMenuItem
$status.Enabled = $false
$last = New-Object System.Windows.Forms.ToolStripMenuItem
$last.Enabled = $false
$runItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Run now'
$autoItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Autorun (unchecked = reminder only)'
$autoItem.CheckOnClick = $true
$autoItem.Checked = [bool]$state.autorun
$reportItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Open latest report'
$settingsItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Settings...'
$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Exit'
[void]$menu.Items.AddRange(@($status, $last, (New-Object System.Windows.Forms.ToolStripSeparator), $runItem, $autoItem,
                             $reportItem, $settingsItem, (New-Object System.Windows.Forms.ToolStripSeparator), $exitItem))
$icon.ContextMenuStrip = $menu

function Update-Menu {
    Read-Settings
    $autoItem.Checked = $state.autorun
    $due = Get-Due
    $day = if ($due.Date -eq (Get-Date).Date) { 'today' } else { 'tomorrow' }
    $left = Format-Left ($due - (Get-Date))
    $what = if ($state.autorun) { 'Auto run' } else { 'Autorun off - reminder' }
    $status.Text = if (Test-Running) { 'Running now...' } else { "$what $day $($state.time), in $left" }
    $last.Text = if ($state.last_run) { "Last run: $($state.last_run)" } else { 'Last run: not yet' }
    $runItem.Enabled = -not (Test-Running)
    $tip = "PC Price Tracker - $($status.Text)"
    $icon.Text = $tip.Substring(0, [math]::Min(63, $tip.Length))  # Windows caps tray tooltips at 63 chars
}

function Start-Run {
    if (Test-Running) { return }
    $script:proc = Start-Process cmd.exe -ArgumentList "/c `"$bat`"" -WorkingDirectory $dir -PassThru
    $state.last_run = (Get-Date).ToString('yyyy-MM-dd HH:mm')
    $state.handled = Get-Today  # a manual run counts as today's run
    Save-State
    Update-Menu
}

function Show-Reminder {
    $script:reminding = $true
    $icon.ShowBalloonTip(15000, 'PC Price Tracker', "Time for today's price run. Click here to start it.", 'Info')
}

function Test-Due {
    $now = Get-Date
    $due = Get-Due
    if ($now -lt $due) { return }
    $state.handled = Get-Today
    Save-State
    if ($state.autorun -and ($now - $due).TotalMinutes -lt $LATE_MINUTES) { Start-Run } else { Show-Reminder }
}

$runItem.add_Click({ Start-Run })
$autoItem.add_Click({
    $s = Read-Json $settingsFile
    $s.autorun = $autoItem.Checked
    Write-Json $settingsFile $s
    Update-Menu
})
$reportItem.add_Click({
    $latest = Get-ChildItem $output -Filter 'pc_vs_parts_*.html' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($latest) { Start-Process $latest.FullName } else { $icon.ShowBalloonTip(5000, 'PC Price Tracker', 'No report yet.', 'Info') }
})
$settingsItem.add_Click({
    try { Start-Process pythonw.exe -ArgumentList "`"$(Join-Path $dir 'settings_app.py')`"" -WorkingDirectory $dir -ErrorAction Stop }
    catch { $icon.ShowBalloonTip(8000, 'PC Price Tracker', "Couldn't open Settings: $($_.Exception.Message)", 'Error') }
})
$exitItem.add_Click({ $icon.Visible = $false; $icon.Dispose(); [System.Windows.Forms.Application]::Exit() })
$menu.add_Opening({ Update-Menu })
$icon.add_BalloonTipClicked({ if ($script:reminding) { $script:reminding = $false; Start-Run } })
$icon.add_BalloonTipClosed({ $script:reminding = $false })
$icon.add_MouseUp({
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {  # left click opens the same menu as right click
        [System.Windows.Forms.NotifyIcon].GetMethod('ShowContextMenu', [System.Reflection.BindingFlags]'Instance,NonPublic').Invoke($icon, $null)
    }
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 20000
$timer.add_Tick({ Test-Due; Update-Menu })
$timer.Start()

Update-Menu
Test-Due
[System.Windows.Forms.Application]::Run()
$mutex.ReleaseMutex()
