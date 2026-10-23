extends RefCounted
const Release = preload("res://src/updates/release.gd")
const Bootstrap = preload("res://src/updates/bootstrap.gd")

static func windows_script(root: String, cache: String, pid: int, repository: String, show_errors := true) -> String:
	# One native PowerShell process waits for our executable to close. All
	# filesystem operations stay in that shell, use literal paths, and verify
	# the final absolute installation path again before removing anything.
	return """$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $env:TEMP
[Environment]::CurrentDirectory = $env:TEMP
$target = '%s'
$cache = '%s'
$repository = '%s'
function Remove-RabbitTree([string]$path) {
  if (-not (Test-Path -LiteralPath $path)) { return }
  $entry = Get-Item -LiteralPath $path -Force
  if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    if ($entry.PSIsContainer) { [IO.Directory]::Delete($entry.FullName) }
    else { [IO.File]::Delete($entry.FullName) }
    return
  }
  if ($entry.PSIsContainer) {
    foreach ($child in Get-ChildItem -LiteralPath $entry.FullName -Force) {
      Remove-RabbitTree $child.FullName
    }
    [IO.Directory]::Delete($entry.FullName)
  } else { [IO.File]::Delete($entry.FullName) }
}
try {
  Wait-Process -Id %d -ErrorAction SilentlyContinue
  $resolved = [IO.Path]::GetFullPath($target).TrimEnd('\\')
  if ($resolved -ne $target.TrimEnd('\\') -or $resolved -eq [IO.Path]::GetPathRoot($resolved).TrimEnd('\\') -or $resolved -eq $env:USERPROFILE) { throw 'Invalid installation path' }
  $marker = Get-Content -LiteralPath (Join-Path $resolved '.rabbitlands-install.json') -Raw | ConvertFrom-Json
  if ($marker.repository -ne $repository) { throw 'Unrecognized installation' }
  $owner = Join-Path $resolved '.eloria-launcher-lock/owner.json'
  $lease = Get-Content -LiteralPath $owner -Raw | ConvertFrom-Json
  if ($lease.pid -ne %d) { throw 'Another process opened the installation' }
  $inno = Join-Path $resolved 'unins000.exe'
  if (Test-Path -LiteralPath $inno) {
    $result = Start-Process -FilePath $inno -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -WindowStyle Hidden -Wait -PassThru
    if ($result.ExitCode -ne 0) { throw 'The registered uninstaller did not complete' }
    Remove-RabbitTree $cache
    return
  }
  $guard = [IO.File]::Open($owner, 'Open', 'ReadWrite', 'None')
  try {
    foreach ($entry in Get-ChildItem -LiteralPath $resolved -Force) {
      if ($entry.Name -ne '.eloria-launcher-lock') { Remove-RabbitTree $entry.FullName }
    }
  } finally { $guard.Dispose() }
  Remove-RabbitTree (Join-Path $resolved '.eloria-launcher-lock')
  [IO.Directory]::Delete($resolved)
  Remove-RabbitTree $cache
} catch {
  if (%s) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Rabbit Lands uninstall') | Out-Null
  } else { Write-Error $_.Exception.Message -ErrorAction Continue }
  exit 1
} finally { Remove-Item -LiteralPath $PSCommandPath -Force }
""" % [root.replace("/", "\\").replace("'", "''"), cache.replace("/", "\\").replace("'", "''"), repository.replace("'", "''"), pid, pid, "$true" if show_errors else "$false"]

static func run(host: Node, root: String, confirmed: bool) -> void:
	var error := Bootstrap.root_error(root)
	if error == "" and not confirmed:
		if DisplayServer.get_name() == "headless":
			error = "Uninstall requires explicit confirmation."
		else:
			var dialog := ConfirmationDialog.new()
			dialog.title = "Uninstall Rabbit Lands"
			dialog.dialog_text = "Remove Rabbit Lands and its downloaded game files from:\n%s\n\nPlayer settings will be kept." % root
			dialog.ok_button_text = "Uninstall"
			host.add_child(dialog)
			var choice := {"done": false, "confirmed": false}
			dialog.confirmed.connect(func() -> void: choice.done = true; choice.confirmed = true)
			dialog.canceled.connect(func() -> void: choice.done = true)
			dialog.popup_centered()
			while not choice.done:
				await host.get_tree().process_frame
			dialog.queue_free()
			if not choice.confirmed:
				host.get_tree().quit()
				return
	var guard := Bootstrap.new()
	if error == "":
		error = guard.acquire(root)
	if error != "":
		push_error(error)
		if DisplayServer.get_name() != "headless":
			OS.alert(error, "Rabbit Lands uninstall")
		host.get_tree().quit(1)
		return
	Release.save_json(root.path_join(".rabbitlands-install.json"), {"schema": 1, "repository": Bootstrap.trust().repository})
	if OS.get_name() == "Windows":
		var script := OS.get_environment("TEMP").path_join("RabbitLands-uninstall-%d.ps1" % OS.get_process_id())
		var file := FileAccess.open(script, FileAccess.WRITE)
		if file == null:
			guard.release_lock()
			host.get_tree().quit(1)
			return
		file.store_string(windows_script(root, Release.cache_for(root), OS.get_process_id(), Bootstrap.trust().repository, DisplayServer.get_name() != "headless"))
		file.close()
		var powershell := OS.get_environment("SystemRoot").path_join("System32/WindowsPowerShell/v1.0/powershell.exe")
		if OS.create_process(powershell, ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script]) <= 0:
			guard.release_lock()
			push_error("The uninstall helper could not start.")
			host.get_tree().quit(1)
			return
		# Leave this owner's record intact until the waiting process verifies it.
		# Process exit closes the guard's file handle.
	else:
		guard.release_lock()
		error = "" if Release.remove_tree(root) == OK and Release.remove_tree(Release.cache_for(root)) == OK else "The installation could not be completely removed."
		if error != "":
			push_error(error)
	host.get_tree().quit(0 if error == "" else 1)
