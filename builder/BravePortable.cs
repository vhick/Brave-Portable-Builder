using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

// Portable launcher for Brave stable on Windows.
// Does not install Brave, register URL handlers, bypass encryption, or change the registry.
// The official Brave executable is left unmodified.
static class BravePortable
{
    static string QuoteArgument(string value)
    {
        // Compatible with Windows CommandLineToArgvW parsing.
        if (value.Length > 0 && value.IndexOfAny(new char[] { ' ', '\t', '\n', '\v', '"' }) < 0)
            return value;
        StringBuilder result = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { backslashes++; continue; }
            if (c == '"')
            {
                result.Append('\\', backslashes * 2 + 1);
                result.Append('"');
                backslashes = 0;
            }
            else
            {
                result.Append('\\', backslashes);
                backslashes = 0;
                result.Append(c);
            }
        }
        result.Append('\\', backslashes * 2);
        result.Append('"');
        return result.ToString();
    }

    [STAThread]
    static int Main(string[] args)
    {
        string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string app = Path.Combine(root, @"App\Brave");
        string exe = Path.Combine(app, "brave.exe");
        string profile = Path.Combine(root, @"Data\User Data");
        string legacyProfile = Path.Combine(root, @"Data\Profile");
        string cache = Path.Combine(root, @"Data\Cache");
        string temp = Path.Combine(root, @"Data\Temp");

        try
        {
            if (!File.Exists(exe))
            {
                MessageBox.Show("Cannot find App\\Brave\\brave.exe. Re-extract the complete ZIP.",
                                "Brave Portable", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 2;
            }

            // Do not silently start with a fresh profile if an older build has data.
            // Let the user close Brave, back up Data, and rename Profile -> User Data.
            bool legacyHasData = Directory.Exists(legacyProfile) &&
                                 Directory.GetFileSystemEntries(legacyProfile).Length > 0;
            bool newHasData = Directory.Exists(profile) &&
                              Directory.GetFileSystemEntries(profile).Length > 0;
            if (legacyHasData && !newHasData)
            {
                MessageBox.Show(
                    "Existing Brave browsing data was detected in Data\\Profile.\n\n" +
                    "Please close every Brave window, back up the complete Data folder, " +
                    "then rename Data\\Profile to Data\\User Data.\n\n" +
                    "Your existing profile was not changed.",
                    "Brave Portable - Profile folder update", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return 5;
            }

            Directory.CreateDirectory(profile);
            Directory.CreateDirectory(cache);
            Directory.CreateDirectory(temp);
            Directory.CreateDirectory(Path.Combine(root, @"Data\Downloads"));

            ProcessStartInfo info = new ProcessStartInfo(exe);
            info.UseShellExecute = false;
            info.WorkingDirectory = app;
            info.EnvironmentVariables["TEMP"] = temp;
            info.EnvironmentVariables["TMP"] = temp;

            // Never allow a passed-in argument to replace the portable profile or cache path.
            foreach (string arg in args)
            {
                if (arg.StartsWith("--user-data-dir", StringComparison.OrdinalIgnoreCase) ||
                    arg.StartsWith("--disk-cache-dir", StringComparison.OrdinalIgnoreCase) ||
                    arg.StartsWith("--profile-directory", StringComparison.OrdinalIgnoreCase))
                {
                    MessageBox.Show("A profile/cache override was blocked to protect your portable data.",
                                    "Brave Portable", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return 3;
                }
            }

            StringBuilder commandLine = new StringBuilder();
            commandLine.Append("--user-data-dir=").Append(QuoteArgument(profile));
            commandLine.Append(" --disk-cache-dir=").Append(QuoteArgument(cache));
            commandLine.Append(" --no-first-run --no-default-browser-check");
            foreach (string arg in args)
                commandLine.Append(' ').Append(QuoteArgument(arg));
            info.Arguments = commandLine.ToString();

            using (Process process = Process.Start(info))
            {
                if (process == null) return 4;
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "Brave Portable", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
