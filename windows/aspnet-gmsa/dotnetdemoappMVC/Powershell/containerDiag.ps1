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
    Gather Windows Container & Windows Node Diagnostic Information

  .DESCRIPTION
    This script was written to gather various attributes (Platform & Guest OS) from the
    Windows Container running in a deployment on Google Kubernetes Engine (GKE) as well
    as the Windows Node in the Node Pool.
#>

##### Script Error Behavior #####

$ErrorActionPreference = “silentlycontinue”

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

function Test-MetadataServerConnection {
    $WebCheckDnsName = (Invoke-WebRequest -UseBasicParsing -Uri http://metadata.google.internal).StatusCode
    $WebCheckIp = (Invoke-WebRequest -UseBasicParsing -Uri http://169.254.169.254).StatusCode
    
    If(($WebCheckDnsName -ne 200) -or ($WebCheckIp -ne 200)) {
            return $FALSE
    }Else {
            return $TRUE
    }
}

function Get-InstanceMetadata ($Property) {
    Invoke-RestMethod http://metadata.google.internal/computeMetadata/v1/instance/$Property -Headers @{"Metadata-Flavor"="Google"}
}

function Get-ContainerInfo {
    $ContainerName = hostname
    $ContainerOsBuild = (Get-ItemProperty -Path "HKLM:\Software\Microsoft\Windows NT\CurrentVersion").CurrentBuild
    $ContainerOsReleaseId = (Get-ItemProperty -Path "HKLM:\Software\Microsoft\Windows NT\CurrentVersion").ReleaseID
    $ContainerPrivIp = (Get-NetIPAddress -InterfaceAlias vEthernet* -AddressFamily IPv4).IPAddress
    $ContainerPubIp = ((Invoke-WebRequest -UseBasicParsing -Uri http://icanhazip.com).Content).Replace("`n","")
    $ContainerDns = (Get-DnsClientServerAddress -InterfaceAlias vEthernet* -AddressFamily IPv4).ServerAddresses

    Log-Message -LogType "Info" -Message "Container Information" -NoExtraLine $TRUE
    Log-Message -LogType "NoTag" -Message "---------------------" -NoExtraLine $TRUE
    Log-Message -LogType "NoTag" -Message "Container Name          : $ContainerName" -NoExtraLine $TRUE
    Log-Message -LogType "NoTag" -Message "Container OS Build      : $ContainerOsBuild" -NoExtraLine $TRUE
    Log-Message -LogType "NoTag" -Message "Container OS Release ID : $ContainerOsReleaseId" -NoExtraLine $TRUE
    Log-Message -LogType "NoTag" -Message "Container Private IP    : $ContainerPrivIP" -NoExtraLine $TRUE
    Log-Message -LogType "NoTag" -Message "Container Public IP     : $ContainerPubIp" -NoExtraLine $TRUE
    Log-Message -LogType "NoTag" -Message "Container DNS Servers   : $ContainerDns"
}

function Get-NodeInfo {
    
    $TestMetadataServerConnection = Test-MetadataServerConnection
    
    If ($TestMetadataServerConnection -eq $FALSE) {
        Log-Message -LogType "Error" -Message "Failed one or more connectivity tests to Metadata Server: metadata.google.internal"
        Log-Message -LogType "Error" -Message "Skipping Node Information section due to connectivity issues with Metadata Server: metadata.google.internal"
    } Else {
        Log-Message -LogType "Info" -Message "Passed connectivity tests to Metadata Server: metadata.google.internal"

        $NodeName = Get-InstanceMetadata -Property name
        $NodeOsName = Get-InstanceMetadata -Property "guest-attributes/guestInventory/Hostname"
        $NodeOsBuild = Get-InstanceMetadata -Property "guest-attributes/guestInventory/Version"
        $NodePrivIp = Get-InstanceMetadata -Property "network-interfaces/0/ip"
        $NodePubIp = Get-InstanceMetadata -Property "network-interfaces/0/forwarded-ips/0"
        $NodeZone = (Get-InstanceMetadata -Property "zone").Split("/")[-1]
        $NodeMachineType = (Get-InstanceMetadata -Property "machine-type").Split("/")[-1]

        Log-Message -LogType "Info" -Message "Node Information" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "----------------" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "Node Metadata Name      : $NodeName" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "Node OS Name            : $NodeOsName" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "Node OS Build           : $NodeOsBuild" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "Node Private IP         : $NodePrivIp" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "Node Public IP          : $NodePubIp" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "Node Zone               : $NodeZone" -NoExtraLine $TRUE
        Log-Message -LogType "NoTag" -Message "Node Machine Type       : $NodeMachineType"
    }
}

##### Main #####

Log-Message -LogType "BannerStart"
Get-Timestamp -ScriptExecutionPosition "Start"
Get-ContainerInfo
Get-NodeInfo
Get-Timestamp -ScriptExecutionPosition "End"
Log-Message -LogType "BannerEnd"