// SPDX-License-Identifier: MIT
import AppKit
import Foundation
import WebKit

final class Host: NSObject, WKNavigationDelegate, NSWindowDelegate {
    private let window: NSWindow
    private var view: WKWebView?
    private var navigationID: Int?
    private var status = 200

    override init() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let browser = WKWebView(frame: NSRect(x: 0, y: 0, width: 1100, height: 800), configuration: config)
        window = NSWindow(contentRect: browser.frame, styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        view = browser
        super.init()
        browser.autoresizingMask = [.width, .height]
        browser.navigationDelegate = self
        window.contentView = browser
        window.title = "BOOTH-Reader — private login"
        window.delegate = self
        if !CommandLine.arguments.contains("--headless") {
            window.makeKeyAndOrderFront(nil)
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
    }

    private func reply(_ id: Int, _ value: Any = NSNull(), error: String? = nil) {
        var response: [String: Any] = ["id": id, "value": value]
        if let error = error { response["error"] = error }
        guard let data = try? JSONSerialization.data(withJSONObject: response, options: [.sortedKeys]) else { return }
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data([10]))
    }

    func command(_ request: [String: Any]) {
        guard let id = request["id"] as? Int, let operation = request["op"] as? String, let browser = view else { return }
        switch operation {
        case "state":
            reply(id, ["url": browser.url?.absoluteString ?? "about:blank", "title": browser.title ?? ""])
        case "goto":
            guard navigationID == nil, let text = request["url"] as? String, let url = URL(string: text), ["https", "http", "data", "about"].contains(url.scheme ?? "") else {
                reply(id, error: "Invalid navigation request")
                return
            }
            navigationID = id
            status = 200
            browser.load(URLRequest(url: url))
        case "evaluate":
            guard let script = request["script"] as? String else { reply(id, error: "Missing script"); return }
            browser.evaluateJavaScript(script) { value, error in
                if let error = error { self.reply(id, error: "WebKit evaluation failed (\((error as NSError).code))") }
                else { self.reply(id, value ?? NSNull()) }
            }
        case "resize":
            guard let width = request["width"] as? Double, let height = request["height"] as? Double, width > 0, height > 0, width <= 16384, height <= 16384 else { reply(id, error: "Invalid viewport"); return }
            window.setContentSize(NSSize(width: width, height: height))
            browser.frame.size = NSSize(width: width, height: height)
            reply(id, true)
        case "cookies":
            browser.configuration.websiteDataStore.httpCookieStore.getAllCookies { cookies in
                let values: [[String: Any]] = cookies.map { cookie in
                    let sameSite = cookie.properties?[HTTPCookiePropertyKey("SameSite")] as? String ?? "Lax"
                    return ["name": cookie.name, "value": cookie.value, "domain": cookie.domain, "path": cookie.path,
                            "secure": cookie.isSecure, "httpOnly": cookie.isHTTPOnly,
                            "expires": cookie.expiresDate?.timeIntervalSince1970 ?? -1,
                            "sameSite": ["Strict", "None", "Lax"].contains(sameSite) ? sameSite : "Lax"]
                }
                self.reply(id, values)
            }
        case "close":
            reply(id, true)
            stop()
        default:
            reply(id, error: "Unknown operation")
        }
    }

    func stop() {
        view?.stopLoading()
        view?.navigationDelegate = nil
        view = nil
        window.contentView = nil
        NSApplication.shared.terminate(nil)
    }

    func windowWillClose(_ notification: Notification) { stop() }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if navigationResponse.isForMainFrame, let response = navigationResponse.response as? HTTPURLResponse { status = response.statusCode }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard let id = navigationID else { return }
        navigationID = nil
        reply(id, ["status": status, "url": webView.url?.absoluteString ?? "", "title": webView.title ?? ""])
    }

    private func failed(_ error: Error) {
        guard let id = navigationID else { return }
        navigationID = nil
        reply(id, error: "WebKit navigation failed (\((error as NSError).code))")
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { failed(error) }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { failed(error) }
}

let app = NSApplication.shared
app.setActivationPolicy(CommandLine.arguments.contains("--headless") ? .accessory : .regular)
let host = Host()
DispatchQueue.global(qos: .userInitiated).async {
    while let line = readLine() {
        guard line.utf8.count <= 1048576, let data = line.data(using: .utf8), let request = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
        DispatchQueue.main.async { host.command(request) }
    }
    DispatchQueue.main.async { host.stop() }
}
app.run()
