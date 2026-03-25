# PowerShell Script to Get Debug SHA-1 Fingerprint
# This script extracts the SHA-1 fingerprint from the Android debug keystore

Write-Host 'Getting Debug SHA-1 Fingerprint for Dev Flavor...' -ForegroundColor Green
Write-Host ''

# Default Android debug keystore location
$debugKeystorePath = "$env:USERPROFILE\.android\debug.keystore"
$debugKeystorePassword = 'android'
$debugKeyAlias = 'androiddebugkey'

try {
    # Try to find keytool in common locations
    $keytoolPaths = @(
        'keytool',
        'C:\Program Files\Java\jdk-*\bin\keytool.exe',
        'C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe',
        "$env:JAVA_HOME\bin\keytool.exe"
    )

    $keytoolPath = $null
    foreach ($path in $keytoolPaths) {
        if ($path -eq 'keytool') {
            # Try to use keytool from PATH
            $keytoolCheck = Get-Command keytool -ErrorAction SilentlyContinue
            if ($keytoolCheck) {
                $keytoolPath = 'keytool'
                break
            }
        } else {
            $resolved = @(Resolve-Path $path -ErrorAction SilentlyContinue)
            if ($resolved.Count -gt 0) {
                $firstPath = $resolved[0].Path
                if (Test-Path $firstPath) {
                    $keytoolPath = $firstPath
                    break
                }
            }
        }
    }

    if (-not $keytoolPath) {
        Write-Host 'Error: keytool not found' -ForegroundColor Red
        Write-Host 'Please install Java JDK or Android Studio, or add Java bin to PATH' -ForegroundColor Red
        Write-Host ''
        Write-Host 'Then run (use full path to keytool.exe if not on PATH):' -ForegroundColor Yellow
        Write-Host ('keytool -list -v -keystore "' + $debugKeystorePath + '" -alias ' + $debugKeyAlias + ' -storepass ' + $debugKeystorePassword + ' -keypass ' + $debugKeystorePassword) -ForegroundColor White
        exit 1
    }

    Write-Host ('Using keytool: ' + $keytoolPath) -ForegroundColor Cyan
    Write-Host ('Debug keystore: ' + $debugKeystorePath) -ForegroundColor Cyan
    Write-Host ''

    if (-not (Test-Path $debugKeystorePath)) {
        Write-Host ('Debug keystore not found at: ' + $debugKeystorePath) -ForegroundColor Yellow
        Write-Host 'This is normal if you have not built an Android app yet.' -ForegroundColor Yellow
        Write-Host 'The keystore will be created automatically on first build.' -ForegroundColor Yellow
        Write-Host ''
        Write-Host 'To create it manually, run:' -ForegroundColor Yellow
        Write-Host ('keytool -genkey -v -keystore "' + $debugKeystorePath + '" -alias ' + $debugKeyAlias + ' -keyalg RSA -keysize 2048 -validity 10000 -storepass ' + $debugKeystorePassword + ' -keypass ' + $debugKeystorePassword) -ForegroundColor White
        exit 1
    }

    Write-Host 'Extracting SHA-1 fingerprint from debug keystore...' -ForegroundColor Yellow
    Write-Host ''

    # Get the SHA-1 fingerprint
    if ($keytoolPath -eq 'keytool') {
        $output = & keytool -list -v -keystore $debugKeystorePath -alias $debugKeyAlias -storepass $debugKeystorePassword -keypass $debugKeystorePassword 2>&1
    } else {
        $output = & $keytoolPath -list -v -keystore $debugKeystorePath -alias $debugKeyAlias -storepass $debugKeystorePassword -keypass $debugKeystorePassword 2>&1
    }

    if ($LASTEXITCODE -eq 0) {
        # Extract SHA-1 from the output
        $sha1Line = $output | Where-Object { $_ -match 'SHA1:' }
        if ($sha1Line) {
            $sha1 = ($sha1Line -split 'SHA1: ')[1].Trim()
            Write-Host 'Debug SHA-1 Fingerprint Found:' -ForegroundColor Green
            Write-Host ('   ' + $sha1) -ForegroundColor Cyan
            Write-Host ''
            Write-Host 'Next Steps (Google Sign-In):' -ForegroundColor Magenta
            Write-Host '1. Go to Firebase Console: https://console.firebase.google.com/' -ForegroundColor White
            Write-Host '2. Select project: ask-the-elect-bfa69' -ForegroundColor White
            Write-Host '3. Project Settings -> Your apps -> Android app (com.mla.asktheelect)' -ForegroundColor White
            Write-Host ('4. Add fingerprint -> paste this SHA-1: ' + $sha1) -ForegroundColor White
            Write-Host '5. Download google-services.json and replace android/app/google-services.json' -ForegroundColor White
            Write-Host '   See: mobile/instructions/firebase-google-signin-setup.md' -ForegroundColor Cyan
            Write-Host ''

            # Copy to clipboard if possible
            try {
                $sha1 | Set-Clipboard
                Write-Host 'SHA-1 fingerprint copied to clipboard!' -ForegroundColor Green
            } catch {
                Write-Host 'Could not copy to clipboard automatically' -ForegroundColor Yellow
            }
        } else {
            Write-Host 'Could not find SHA-1 fingerprint in the output' -ForegroundColor Red
            Write-Host 'Output:' -ForegroundColor Yellow
            Write-Host $output
        }
    } else {
        Write-Host ('Failed to extract SHA-1 fingerprint. Exit code: ' + $LASTEXITCODE) -ForegroundColor Red
        Write-Host ('Output: ' + $output) -ForegroundColor Red
    }

} catch {
    Write-Host ('Error getting SHA-1 fingerprint: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ''
    Write-Host 'Manual command (run from this folder):' -ForegroundColor Yellow
    $keytoolCmd = if ($keytoolPath -and $keytoolPath -ne 'keytool') {
        '& "' + $keytoolPath + '" -list -v -keystore "' + $debugKeystorePath + '" -alias ' + $debugKeyAlias + ' -storepass ' + $debugKeystorePassword + ' -keypass ' + $debugKeystorePassword
    } else {
        'keytool -list -v -keystore "' + $debugKeystorePath + '" -alias ' + $debugKeyAlias + ' -storepass ' + $debugKeystorePassword + ' -keypass ' + $debugKeystorePassword
    }
    Write-Host $keytoolCmd -ForegroundColor White
}
