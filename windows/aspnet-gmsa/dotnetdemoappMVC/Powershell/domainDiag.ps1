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

<#
  .SYNOPSIS
    Test connectivity to Active Directory Domain and verify gMSA Account

  .DESCRIPTION
    This script was written to perform various connectiviy tests to the Active Directory
    Domain and also to verify the gMSA Account is valid and usable on the Windows Node Pool.
    
#>

##### Script Error Behavior #####

$ErrorActionPreference = "silentlycontinue"

##### Params Declaration #####

$GmsaName=$args[0]

##### Param Check #####

If ($GmsaName -eq $null) {
    Log-Message -LogType "Error" -Message "Script requires a gMSA Name to run. Please specify one in the text box and try again."
    Log-Message -LogType "Term"
    Exit
}

##### Functions #####

function Get-TimeStamp ($ScriptExecutionPosition="default") {
    $Timestamp = Get-Date -Format "MM-dd-yyyy-HH:mm:ss"
    switch ($ScriptExecutionPosition) {
        "Start" {
            Log-Message -LogType "Info" -Message "Starting script execution at $Timestamp"  
        }
        "End" {
            Log-Message -LogType "Info" -Message "Script execution complete at $Timestamp"  
        }
        "default" {
            Log-Message -LogType "Info" -Message "Timestamp: $Timestamp"
        }
    }
}

function Log-Message ($LogType, $Message, $NoExtraLine) {
    switch ($LogType) {
        "BannerStart" {
            Write-Output "*****   C O N T A I N E R   D I A G N O S T I C S   *****"
            Log-Message -LogType "EmptyLine" -NoExtraLine $NoExtraLine
        }
        "BannerEnd" {
            Write-Output "*****      E N D   O F   D I A G N O S T I C S      *****"
            Log-Message -LogType "EmptyLine" -NoExtraLine $NoExtraLine
        }
        "EmptyLine" {
            If (($NoExtraLine -eq $FALSE) -or (!$NoExtraLine)) {
                Write-Output ""
            }
        }
        "NoTag" {
            Write-Output "        $Message"
            Log-Message -LogType "EmptyLine" -NoExtraLine $NoExtraLine
        }
        "Info" {
            Write-Output "[INFO]  $Message"
            Log-Message -LogType "EmptyLine" -NoExtraLine $NoExtraLine
        }
        "Pass" {
            Write-Output "[PASS]  $Message"
            Log-Message -LogType "EmptyLine" -NoExtraLine $NoExtraLine
        }
        "Error" {
            Write-Output "[ERROR] $Message"
            Log-Message -LogType "EmptyLine" -NoExtraLine $NoExtraLine
        }
        "Term" {
            Write-Output "[TERM]  Exiting"
            Log-Message -LogType "EmptyLine" -NoExtraLine $NoExtraLine
            Log-Message -LogType "End"
        }
        "default" {
            Write-Output "        $Message"
        }
    }
}

function Check-gMSA ($GmsaCheckAccount) {
    $Account=(Get-ADServiceAccount $GmsaCheckAccount -ErrorVariable IfExists)
    If ($IfExists -like "*unable to find a default server*") {
        Log-Message -LogType "Error" -Message "Cannot query Active Directory!"
        Log-Message -LogType "Error" -Message "Confirm that the Container is running with a Credential Spec file and the Node is authorized to use $GmsaCheckAccount"
        Log-Message -LogType "Term"
        Exit
    } Elseif ($IfExists -like "*cannot find an object with identity*") {
        Log-Message -LogType "Error" -Message "This gMSA Name does not exist in Active Directory!"
        Log-Message -LogType "Error" -Message "Please double check the Account Name and re-enter the correct account in the text box."
        Log-Message -LogType "Term"
        Exit
    } Elseif ($IfExists -like "*") {
        Log-Message -LogType "Error" -Message "Unknown error!"
        Log-Message -LogType "Info" -Message "Error Text: $IfExists"
        Log-Message -LogType "Term"
        Exit
    } Elseif ($IfExists.Count -eq 0) {
        Log-Message -LogType "Pass" -Message "gMSA Account found in Active Directory" -NoExtraLine $True
        Log-Message -LogType "NoTag" -Message "$Account"

        $ContainerName = hostname
        $TestSucceeded= Test-ADServiceAccount $GmsaCheckAccount -ErrorVariable HasAccess
        if ($TestSucceeded) {
            Log-Message -LogType "Pass" -Message "This Container ($ContainerName) is running on a GKE Windows Node that is authorized to use $GmsaCheckAccount"
        } else {
            if ($TestSucceeded -eq $False -or $HasAccess -like "*Access Denied*") {
               Log-Message -LogType "Error" -Message "This Container ($ContainerName) is not running on a GKE Windows Node that is authorized to use $GmsaCheckAccount"
               Log-Message -LogType "Info" -Message "*** Active Directory Authentication will fail. ***"
            } else {
                Log-Message -LogType "Error" -Message "Unknown error!"
                Log-Message -LogType "Info" -Message "Error Text: $HasAccess"
                Log-Message -LogType "Term"
                Exit
            }            
        }
    }
}

function Check-Schannel {
    If ((Test-ComputerSecureChannel) -eq $True) {
        Log-Message -LogType "Pass" -Message "Computer Secure Channel test has passed"
     } Else {
        Log-Message -LogType "Error" -Message "Computer Secure Channel test has failed"
        Log-Message -LogType "Term"
        Exit
    }
}


##### Main #####

Log-Message -LogType "BannerStart"
Get-Timestamp -ScriptExecutionPosition "Start"
Log-Message -LogType "Info" -Message "Using gMSA: $GmsaName"
Check-Schannel
Check-gMSA ($GmsaName)
Get-Timestamp -ScriptExecutionPosition "End"
Log-Message -LogType "BannerEnd"