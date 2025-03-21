# Consolidate JSON files based on file_path
# Usage: .\ConsolidateJson.ps1 -FolderPath "D:\path\to\json\files"

param (
    [Parameter(Mandatory=$true)]
    [string]$FolderPath
)

# Ensure the folder path exists
if (-not (Test-Path -Path $FolderPath -PathType Container)) {
    Write-Error "The specified folder path does not exist: $FolderPath"
    exit 1
}

# Get all JSON files in the specified directory
$jsonFiles = Get-ChildItem -Path $FolderPath -Filter "*.json"

if ($jsonFiles.Count -eq 0) {
    Write-Warning "No JSON files found in: $FolderPath"
    exit 0
}

Write-Host "Found $($jsonFiles.Count) JSON files to process."

# Dictionary to group files by file_path
$filePathGroups = @{}

# Process each JSON file
foreach ($file in $jsonFiles) {
    try {
        # Read and parse the JSON content
        $jsonContent = Get-Content -Path $file.FullName -Raw | ConvertFrom-Json
        
        # Check if the JSON has the required file_path property
        if (-not (Get-Member -InputObject $jsonContent -Name "file_path" -MemberType Properties)) {
            Write-Warning "Skipping $($file.Name): Missing 'file_path' property"
            continue
        }
        
        # Extract the file_path
        $filePath = $jsonContent.file_path
        
        # Create a simplified object with just the required properties
        $simpleObject = @{
            "output_path" = $jsonContent.output_path
            "response" = $jsonContent.response
        }
        
        # Add to the appropriate group
        if (-not $filePathGroups.ContainsKey($filePath)) {
            $filePathGroups[$filePath] = @()
        }
        
        $filePathGroups[$filePath] += $simpleObject
    }
    catch {
        Write-Warning "Error processing $($file.Name): $_"
    }
}

Write-Host "Grouped files into $($filePathGroups.Count) distinct file_path entries."

# Create consolidated JSON files
foreach ($filePath in $filePathGroups.Keys) {
    try {
        # Generate output filename based on the original path
        $fileName = [System.IO.Path]::GetFileNameWithoutExtension($filePath)
        $outputFileName = "$fileName-consolidated.json"
        $outputPath = Join-Path -Path $FolderPath -ChildPath $outputFileName
        
        # Create the consolidated object
        $consolidatedObject = @{
            $filePath = $filePathGroups[$filePath]
        }
        
        # Convert to JSON and save
        $consolidatedJson = $consolidatedObject | ConvertTo-Json -Depth 10
        $consolidatedJson | Out-File -FilePath $outputPath -Encoding utf8
        
        Write-Host "Created consolidated file: $outputFileName with $($filePathGroups[$filePath].Count) entries"
    }
    catch {
        Write-Warning "Error creating consolidated file for '$filePath': $_"
    }
}

Write-Host "Consolidation complete."
