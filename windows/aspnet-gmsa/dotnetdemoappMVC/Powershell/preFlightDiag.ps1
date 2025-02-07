# Copyright 2021 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

$ChecksPassed = $null
$CheckAdPowerShell = (Get-Command Test-ADServiceAccount).ModuleName
$IisDocRoot = "C:\inetpub\wwwroot\"
$PowerShellScriptRoot = "C:\inetpub\wwwroot\Powershell\"
If ($CheckAdPowerShell -eq 'ActiveDirectory') {
    Write-Output "[PASS]  Active Directory RSAT Powershell Module Installed`n" 
    If ($ChecksPassed -eq $null) {
        $ChecksPassed = $TRUE
    }
} Else {
    Write-Output "[FAIL]  Active Directory RSAT Powershell Module Missing"
    Write-Output "        Please add dependency in Dockerfile or install the tools interactively on the Container`n"
    Write-Output "        Dockerfile: RUN Add-WindowsFeature RSAT-AD-Powershell";
    If ($ChecksPassed -eq $null) {
        $ChecksPassed = $FALSE
    }
}

$CheckIisDocRoot = Test-Path $iisDocRoot
If ($CheckIisDocRoot -eq $TRUE) {
    Write-Output "[PASS]  IIS Document Root found"
    Write-Output "        $iisDocRoot`n"
    If ($ChecksPassed -eq $TRUE) {
        $ChecksPassed = $TRUE
    }
}
Else {
    Write-Output "[FAIL]  IIS Document Root is not correct"
    Write-Output "        Please ensure that all WebApp Files are in the $IisDocRoot Folder`n"
    $ChecksPassed = $FALSE
}

$CheckPowerShellRoot = Test-Path $PowerShellScriptRoot
If ($CheckPowerShellRoot -eq $TRUE) {
    Write-Output "[PASS]  Powershell Scripts Folder found"
    Write-Output "        $PowerShellScriptRoot`n"
    If ($ChecksPassed -eq $TRUE) {
        $ChecksPassed = $TRUE
    }
} Else {
    Write-Output "[FAIL]  Powershell Scripts Folder not found"
    Write-Output "        Please ensure that all Powershell Scripts are in the $PowerShellScriptRoot Folder`n"
    $ChecksPassed = $FALSE
    }
    $CheckContainerPs = Test-Path "$PowerShellScriptRoot\containerDiag.ps1"
    If ($CheckContainerPs -eq $TRUE) {
        Write-Output "[PASS]  Container Diagnostic Script found"
        Write-Output "        $PowerShellScriptRoot\containerDiag.ps1`n"
        If ($ChecksPassed -eq $TRUE) {
            $ChecksPassed = $TRUE
        }
    } Else {
        Write-Output "[FAIL]  Container Diagnostic Script not found"
        Write-Output "        Please ensure that all Powershell Scripts are in the $PowerShellScriptRoot Folder`n"
        $ChecksPassed = $FALSE
    }
;$CheckDomainPs = Test-Path "$PowerShellScriptRoot\domainDiag.ps1"
If ($CheckDomainPs -eq $TRUE) {
    Write-Output "[PASS]  Domain Diagnostic Script found"
    Write-Output "        $PowerShellScriptRoot\domainDiag.ps1`n"
    If ($ChecksPassed -eq $TRUE) {
        $ChecksPassed = $TRUE
    }
} Else { 
    Write-Output "[FAIL]  Domain Diagnostic Script not found"
    Write-Output "        Please ensure that all Powershell Scripts are in the $PowerShellScriptRoot Folder`n"
    $ChecksPassed = $FALSE
}

If ($ChecksPassed -eq $TRUE) {
    Write-Output "[RES]   Result: PASS   All checks passed! Please proceed to run the different tests."
} Else { 
    Write-Output "[RES]   Result: FAIL   One of more prerequisite checks failed. Please fix the issues and re-run the checks before proceeding"
}