// Copyright 2021 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Web;
using System.Web.Mvc;
using System.Management.Automation;
using System.Text;

namespace DotNetDemoAppMvc.Controllers
{
    public class PowershellController : Controller
    {
        public ActionResult Index()
        {
            return View();
        }
        public ActionResult PreFlightChecks()
        {
            var result = RunPowershellScript("C:\\inetpub\\wwwroot\\Powershell\\preFlightDiag.ps1");
            return Content(result);
        }

        public ActionResult ContainerDiagnostics()
        {
            var result = RunPowershellScript("C:\\inetpub\\wwwroot\\Powershell\\containerDiag.ps1");
            return Content(result);
        }

        public ActionResult DomainDiagnostics(string gMSAInput)
        {
            var result = RunPowershellScript("C:\\inetpub\\wwwroot\\Powershell\\domainDiag.ps1 " + gMSAInput);
            return Content(result);
        }

        private string RunPowershellScript(string command)
        {
            var strBuild = new StringBuilder();
            var powerShell = PowerShell.Create();
            powerShell.Commands.AddScript(command);
            var psOutput = powerShell.Invoke();

            if (psOutput.Count > 0)
            {
                foreach (var psObject in psOutput)
                {
                    strBuild.Append(psObject.BaseObject.ToString() + "\r\n");
                }
            }
            return strBuild.ToString();
        }
    }
}