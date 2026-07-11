param(
    [string]$Language,
    [string]$Title,
    [string]$Slug,
    [switch]$NoOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$Languages = @(
    [pscustomobject]@{
        Code = "zh"
        Name = "中文"
        SlugRequired = $true
        DefaultTags = @("记录")
    },
    [pscustomobject]@{
        Code = "en"
        Name = "English"
        SlugRequired = $false
        DefaultTags = @("Journal")
    },
    [pscustomobject]@{
        Code = "ja"
        Name = "日本語"
        SlugRequired = $true
        DefaultTags = @()
    }
)

function Get-LanguageConfig {
    param([Parameter(Mandatory = $true)][string]$Code)

    $normalizedCode = $Code.Trim().ToLowerInvariant()
    foreach ($item in $Languages) {
        if ($item.Code -eq $normalizedCode) {
            return $item
        }
    }

    $supportedCodes = ($Languages | ForEach-Object { $_.Code }) -join ", "
    throw "不支持的语言 '$Code'。可选语言：$supportedCodes。"
}

function Read-RequiredValue {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$ErrorMessage
    )

    $value = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw $ErrorMessage
    }

    return $value.Trim()
}

function Read-PostLanguage {
    Write-Host "请选择文章语言："
    for ($i = 0; $i -lt $Languages.Count; $i++) {
        $number = $i + 1
        $item = $Languages[$i]
        Write-Host "  $number. $($item.Code) - $($item.Name)"
    }

    while ($true) {
        $choice = Read-Host "输入编号或代码"
        if ([string]::IsNullOrWhiteSpace($choice)) {
            Write-Host "语言不能为空。"
            continue
        }

        $trimmedChoice = $choice.Trim()
        $choiceNumber = 0
        if ([int]::TryParse($trimmedChoice, [ref]$choiceNumber)) {
            if ($choiceNumber -ge 1 -and $choiceNumber -le $Languages.Count) {
                return $Languages[$choiceNumber - 1]
            }
        }

        $normalizedChoice = $trimmedChoice.ToLowerInvariant()
        foreach ($item in $Languages) {
            if ($item.Code -eq $normalizedChoice) {
                return $item
            }
        }

        $supportedCodes = ($Languages | ForEach-Object { $_.Code }) -join ", "
        Write-Host "无法识别 '$choice'。请输入编号或语言代码：$supportedCodes。"
    }
}

function ConvertTo-SafeSlug {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value) {
        return ""
    }

    $safeSlug = $Value.Trim().ToLowerInvariant()
    $safeSlug = $safeSlug -replace "[^a-z0-9-]+", "-"
    $safeSlug = $safeSlug -replace "-{2,}", "-"
    $safeSlug = $safeSlug.Trim("-")

    return $safeSlug
}

function ConvertTo-YamlDoubleQuotedScalar {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value) {
        $Value = ""
    }

    $escaped = $Value.Replace("\", "\\")
    $escaped = $escaped.Replace('"', '\"')
    $escaped = $escaped.Replace("`r", "\r")
    $escaped = $escaped.Replace("`n", "\n")
    $escaped = $escaped.Replace("`t", "\t")

    return '"' + $escaped + '"'
}

function ConvertTo-YamlStringList {
    param([AllowEmptyCollection()][string[]]$Values)

    if ($null -eq $Values -or $Values.Count -eq 0) {
        return @("tags: []")
    }

    $lines = @("tags:")
    foreach ($value in $Values) {
        $lines += "  - $(ConvertTo-YamlDoubleQuotedScalar $value)"
    }

    return $lines
}

function Get-DefaultContentLanguage {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $configPath = Join-Path -Path $RepoRoot -ChildPath "hugo.yaml"
    if (-not (Test-Path -LiteralPath $configPath)) {
        return "en"
    }

    $config = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8)
    $match = [regex]::Match($config, "(?m)^\s*defaultContentLanguage\s*:\s*['""]?([^'""\s#]+)")
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }

    return "en"
}

function Remove-EmptyParentDirectories {
    param(
        [Parameter(Mandatory = $true)][string]$StartDirectory,
        [Parameter(Mandatory = $true)][string]$StopDirectory
    )

    $current = [System.IO.Path]::GetFullPath($StartDirectory)
    $stop = [System.IO.Path]::GetFullPath($StopDirectory)

    while ($current.StartsWith($stop, [System.StringComparison]::OrdinalIgnoreCase)) {
        if (-not (Test-Path -LiteralPath $current)) {
            break
        }

        $children = @(Get-ChildItem -LiteralPath $current -Force)
        if ($children.Count -gt 0) {
            break
        }

        Remove-Item -LiteralPath $current -Force
        if ($current.Equals($stop, [System.StringComparison]::OrdinalIgnoreCase)) {
            break
        }

        $parent = Split-Path -Path $current -Parent
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) {
            break
        }

        $current = $parent
    }
}

function Write-PostFrontMatter {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$PostTitle,
        [Parameter(Mandatory = $true)][string]$PostSlug,
        [Parameter(Mandatory = $true)][string]$Date,
        [string[]]$Tags = @()
    )

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $content = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    $lines = $content -split "\r?\n", -1

    if ($lines.Count -lt 2 -or $lines[0] -ne "---") {
        throw "Hugo 已创建文件，但未找到 YAML Front Matter 起始标记：$Path"
    }

    $frontMatterEndIndex = -1
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -eq "---") {
            $frontMatterEndIndex = $i
            break
        }
    }

    if ($frontMatterEndIndex -lt 0) {
        throw "Hugo 已创建文件，但未找到 YAML Front Matter 结束标记：$Path"
    }

    $bodyLines = @()
    if ($frontMatterEndIndex + 1 -lt $lines.Count) {
        $bodyLines = $lines[($frontMatterEndIndex + 1)..($lines.Count - 1)]
    }

    $tagLines = ConvertTo-YamlStringList -Values $Tags
    $frontMatter = @(
        "---",
        "title: $(ConvertTo-YamlDoubleQuotedScalar $PostTitle)",
        "slug: $(ConvertTo-YamlDoubleQuotedScalar $PostSlug)",
        "date: $Date",
        "lastmod: $Date",
        "draft: true"
    ) + $tagLines + @(
        "cover:",
        '  image: ""',
        "  relative: false",
        "---"
    )

    $newContent = ($frontMatter + $bodyLines) -join "`n"
    [System.IO.File]::WriteAllText($Path, $newContent, $utf8NoBom)
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $Command @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        $details = ($output | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($details)) {
            throw "$FailureMessage 退出码：$exitCode。"
        }

        throw "$FailureMessage 退出码：$exitCode。`n$details"
    }

    return $output
}

try {
    $repoRoot = (Resolve-Path -LiteralPath (Get-Location)).Path

    if ([string]::IsNullOrWhiteSpace($Language)) {
        $languageConfig = Read-PostLanguage
    }
    else {
        $languageConfig = Get-LanguageConfig -Code $Language
    }

    if ([string]::IsNullOrWhiteSpace($Title)) {
        $Title = Read-RequiredValue -Prompt "文章标题" -ErrorMessage "文章标题不能为空。"
    }
    else {
        $Title = $Title.Trim()
        if ([string]::IsNullOrWhiteSpace($Title)) {
            throw "文章标题不能为空。"
        }
    }

    if ($PSBoundParameters.ContainsKey("Slug")) {
        $rawSlug = $Slug
    }
    else {
        $rawSlug = Read-Host "英文或罗马字 slug（英文文章可留空自动生成）"
    }

    if ([string]::IsNullOrWhiteSpace($rawSlug)) {
        if ($languageConfig.SlugRequired) {
            throw "$($languageConfig.Name)文章必须填写英文或罗马字 slug，已停止创建。"
        }

        $rawSlug = $Title
    }

    $safeSlug = ConvertTo-SafeSlug -Value $rawSlug
    if ([string]::IsNullOrWhiteSpace($safeSlug)) {
        throw "slug 安全清理后为空。请使用英文字母、数字或连字符。"
    }

    $today = Get-Date
    $date = $today.ToString("yyyy-MM-dd", [System.Globalization.CultureInfo]::InvariantCulture)
    $year = $today.ToString("yyyy", [System.Globalization.CultureInfo]::InvariantCulture)

    $contentDirRelative = Join-Path -Path "content" -ChildPath $languageConfig.Code
    $postRelativePath = Join-Path -Path (Join-Path -Path "posts" -ChildPath $year) -ChildPath "$safeSlug.md"
    $targetRelativePath = Join-Path -Path $contentDirRelative -ChildPath $postRelativePath
    $targetFullPath = Join-Path -Path $repoRoot -ChildPath $targetRelativePath

    if (Test-Path -LiteralPath $targetFullPath) {
        throw "目标文件已存在，已停止以避免覆盖：$targetFullPath"
    }

    $hugo = Get-Command "hugo" -ErrorAction SilentlyContinue
    if ($null -eq $hugo) {
        throw "找不到 hugo 命令。请确认 Hugo 已安装并加入 PATH。"
    }

    $hugoArgs = @(
        "new",
        "content",
        $targetRelativePath,
        "-k",
        "posts"
    )
    $null = Invoke-ExternalCommand -Command $hugo.Source -Arguments $hugoArgs -FailureMessage "Hugo archetype 生成文章失败。"

    if (-not (Test-Path -LiteralPath $targetFullPath)) {
        $defaultLanguage = Get-DefaultContentLanguage -RepoRoot $repoRoot
        $fallbackRelativePath = Join-Path -Path (Join-Path -Path "content" -ChildPath $defaultLanguage) -ChildPath $targetRelativePath
        $fallbackFullPath = Join-Path -Path $repoRoot -ChildPath $fallbackRelativePath

        if (-not (Test-Path -LiteralPath $fallbackFullPath)) {
            throw "Hugo 命令已完成，但未找到目标文件：$targetFullPath"
        }

        $targetDirectory = Split-Path -Path $targetFullPath -Parent
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
        Move-Item -LiteralPath $fallbackFullPath -Destination $targetFullPath -ErrorAction Stop

        $fallbackCleanupRoot = Join-Path -Path $repoRoot -ChildPath (Join-Path -Path (Join-Path -Path "content" -ChildPath $defaultLanguage) -ChildPath "content")
        Remove-EmptyParentDirectories -StartDirectory (Split-Path -Path $fallbackFullPath -Parent) -StopDirectory $fallbackCleanupRoot
    }

    Write-PostFrontMatter -Path $targetFullPath -PostTitle $Title -PostSlug $safeSlug -Date $date -Tags $languageConfig.DefaultTags

    if (-not $NoOpen) {
        $code = Get-Command "code" -ErrorAction SilentlyContinue
        if ($null -eq $code) {
            throw "文章已创建，但找不到 code 命令，无法自动在 VS Code 中打开：$targetFullPath"
        }

        $codeArgs = @("--reuse-window", $targetFullPath)
        $null = Invoke-ExternalCommand -Command $code.Source -Arguments $codeArgs -FailureMessage "文章已创建，但 VS Code 打开失败。"
    }

    Write-Host "创建成功：$targetFullPath"
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
