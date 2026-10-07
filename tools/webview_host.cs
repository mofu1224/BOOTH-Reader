// Portable WebView2 host (compiles with the OS .NET Framework csc at setup
// time). The SDK WinForms assembly targets .NET Framework 4.x; PowerShell 7
// hosts load a different Forms identity, so the host must be a native exe.
using System;
using System.Drawing;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

public static class BoothWebViewHost {
    [STAThread]
    public static int Main(string[] args) {
        Run(args[0], args[1], int.Parse(args[2]), args.Length > 3 && args[3] == "hidden");
        return Environment.ExitCode;
    }

    public static void Run(string runtime, string profile, int port, bool hidden) {
        Application.EnableVisualStyles();
        using (var window = new Form())
        using (var view = new WebView2()) {
            window.Text = "BOOTH-Reader";
            window.Width = 1100;
            window.Height = 800;
            window.ShowInTaskbar = !hidden;
            try {
                var icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                if (icon != null) window.Icon = icon;
            } catch (Exception) {
            }
            if (hidden) {
                // The startup health check launches this host hidden; keep the window
                // off-screen so it never flashes while WebView2 initializes.
                window.FormBorderStyle = FormBorderStyle.None;
                window.StartPosition = FormStartPosition.Manual;
                window.Location = new Point(-32000, -32000);
            }
            view.Dock = DockStyle.Fill;
            window.Controls.Add(view);
            window.Shown += (sender, args) => {
                try {
                    var options = new CoreWebView2EnvironmentOptions(
                        "--remote-debugging-address=127.0.0.1 --remote-debugging-port=" + port);
                    CoreWebView2Environment.CreateAsync(runtime, profile, options)
                        .ContinueWith(task => view.EnsureCoreWebView2Async(task.Result),
                            TaskScheduler.FromCurrentSynchronizationContext())
                        .Unwrap()
                        .ContinueWith(done => {
                            if (done.IsFaulted) {
                                var error = done.Exception.GetBaseException();
                                Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
                                window.Close();
                                Environment.ExitCode = 1;
                                return;
                            }
                            view.CoreWebView2.Settings.IsPasswordAutosaveEnabled = false;
                            view.CoreWebView2.Settings.IsGeneralAutofillEnabled = false;
                            view.CoreWebView2.Navigate("about:blank");
                            if (hidden) window.Hide();
                        }, TaskScheduler.FromCurrentSynchronizationContext())
                        .ContinueWith(fault => {
                            if (fault.IsFaulted) {
                                var error = fault.Exception.GetBaseException();
                                Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
                            }
                        });
                } catch (Exception error) {
                    Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
                    window.Close();
                    Environment.ExitCode = 1;
                }
            };
            Application.Run(window);
        }
    }
}
