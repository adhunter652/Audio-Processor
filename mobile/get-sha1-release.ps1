# PowerShell script to get SHA-1 fingerprint for release keystore
# This script will help you get the SHA-1 fingerprint needed for Google Sign-In

Write-Host "Getting SHA-1 fingerprint for release keystore..." -ForegroundColor Green

# Try to find Java installation
$javaPaths = @(
    "${env:JAVA_HOME}\bin\keytool.exe",
    "C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe",
    "C:\Program Files\Android\Android Studio\jre\bin\keytool.exe"
)

# Also search for Java installations
$javaInstallations = Get-ChildItem "C:\Program Files\Java" -ErrorAction SilentlyContinue
foreach ($java in $javaInstallations) {
    $javaPaths += "$($java.FullName)\bin\keytool.exe"
}

$javaInstallations32 = Get-ChildItem "C:\Program Files (x86)\Java" -ErrorAction SilentlyContinue
foreach ($java in $javaInstallations32) {
    $javaPaths += "$($java.FullName)\bin\keytool.exe"
}

$keytoolPath = $null
foreach ($path in $javaPaths) {
    if (Test-Path $path) {
        $keytoolPath = $path
        break
    }
}

if (-not $keytoolPath) {
    Write-Host "Java keytool not found. Please install Java or Android Studio." -ForegroundColor Red
    Write-Host "You can also manually run the following command:" -ForegroundColor Yellow
    Write-Host "keytool -list -v -keystore android/upload-keystore.jks -alias upload" -ForegroundColor Cyan
    exit 1
}

Write-Host "Found keytool at: $keytoolPath" -ForegroundColor Green

# Get the keystore password from key.properties
$keyPropertiesPath = "android/key.properties"
if (Test-Path $keyPropertiesPath) {
    $keyProperties = Get-Content $keyPropertiesPath
    $storePassword = ($keyProperties | Where-Object { $_ -match "storePassword=" }) -replace "storePassword=", ""
    $keyPassword = ($keyProperties | Where-Object { $_ -match "keyPassword=" }) -replace "keyPassword=", ""
    
    Write-Host "Using password from key.properties" -ForegroundColor Green
} else {
    Write-Host "key.properties not found. You'll need to enter the password manually." -ForegroundColor Yellow
    $storePassword = ""
    $keyPassword = ""
}

# Run keytool command (prefer android/upload-keystore.jks; key.properties uses this path)
$keystorePath = "android/upload-keystore.jks"
if (-not (Test-Path $keystorePath)) {
    $keystorePath = "android/app/upload-keystore.jks"
}
if (Test-Path $keystorePath) {
    Write-Host "Running keytool command..." -ForegroundColor Green
    
    if ($storePassword -and $keyPassword) {
        # Try with password from key.properties
        & $keytoolPath -list -v -keystore $keystorePath -alias upload -storepass $storePassword -keypass $keyPassword
    } else {
        # Manual password entry
        & $keytoolPath -list -v -keystore $keystorePath -alias upload
    }
} else {
    Write-Host "Keystore file not found at android/upload-keystore.jks or android/app/upload-keystore.jks" -ForegroundColor Red
    Write-Host "Create key.properties and place your release keystore in android/ (see key.properties.example)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "IMPORTANT: Look for the SHA1 fingerprint in the output above." -ForegroundColor Red
Write-Host "It should look like: XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX" -ForegroundColor Yellow
Write-Host "Copy this SHA1 fingerprint and add it to your Firebase Console." -ForegroundColor Green
