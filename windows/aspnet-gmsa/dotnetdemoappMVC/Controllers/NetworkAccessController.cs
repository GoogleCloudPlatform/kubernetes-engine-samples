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
using System.Text;
using System.Web;
using System.Web.Mvc;
using System.Data.SqlClient;

namespace DotNetDemoAppMvc.Controllers
{
    public class NetworkAccessController : Controller
    {
        public ActionResult Index()
        {
            return View();
        }

        public ActionResult SqlServerDiagnostics(string sqlServer)
        {
            var result = new StringBuilder();
            var sqlConnection = new SqlConnection();
            try
            {
                sqlConnection.ConnectionString = $"Server={sqlServer};Integrated Security=true;Initial Catalog=master";
                sqlConnection.Open();
                result.AppendLine("[Pass] Connection to SQL Server was successfull. Authentication with gMSA suceeded.");
            }
            catch (Exception e)
            {
                result.AppendLine("[Error] Error while connecting to SQL Server. Error is: " + e.Message);
            }

            try
            {
                var sqlCommand = sqlConnection.CreateCommand();
                var query = "SELECT name FROM sys.databases";
                sqlCommand.CommandText = query;
                SqlDataReader reader = sqlCommand.ExecuteReader();

                result.AppendLine("[Pass] Executed the query 'SELECT name FROM sys.databases' and found the following databases:");
                while (reader.Read())
                {

                    result.AppendLine(reader.GetString(0));
                }
                reader.Close();
                sqlConnection.Close();
            }
            catch (Exception e)
            {
                result.AppendLine("[Error] Error while querying SQL Server. Error is: " + e.Message);
            }

            return Content(result.ToString());
        }

        public ActionResult FileShareDiagnostics(string filePath)
        {
            var overallSuccess = true;
            var testResult = new StringBuilder();

            if (System.IO.File.Exists(filePath))
            {
                // Test read access
                try
                {
                    testResult.AppendLine($"[Info] Attempting to read from file '{filePath}'");
                    string fileContent = System.IO.File.ReadAllText(filePath);
                    testResult.AppendLine("[Pass] Successfully read file content. Content is:");
                    testResult.AppendLine(fileContent);
                }
                catch (Exception e)
                {
                    overallSuccess = false;
                    testResult.AppendLine("[Error] Could not read file content. Error is:");
                    testResult.AppendLine(e.Message);
                }
                // Test write access 
                try
                {
                    testResult.AppendLine($"[Info] Attempting to append to file '{filePath}'");
                    System.IO.File.AppendAllText(filePath, "Line added by web application", Encoding.UTF8);
                    overallSuccess = false;
                    testResult.AppendLine("[Error] Content was appended to the file. This is not the expected behavior. Please verify the gMSA has only read permissions over the file.");
                }
                catch (UnauthorizedAccessException)
                {
                    testResult.AppendLine("[Pass] gMSA not permitted to append content to the file. This is the expected behavior.");
                }

                catch (Exception e)
                {
                    overallSuccess = false;
                    testResult.AppendLine("[Error] Could not append content to the file. Error is:");
                    testResult.AppendLine(e.Message);
                }
            }
            else
            {
                overallSuccess = false;
                testResult.AppendLine($"[Error] Cloud not find file '{filePath}'. Either the path is incorrect, or the application is not configured to use the gMSA.");
            }

            testResult.AppendLine();

            if (overallSuccess)
            {
                testResult.AppendLine("[Pass] All tests were successful. The application is able to access network shares with the gMSA.");
            }
            else 
            {
                testResult.AppendLine("[Fail] Some or all tests failed. Refer to the error message(s) for additional information.");
            }

            return Content(testResult.ToString());
        }
    }
}