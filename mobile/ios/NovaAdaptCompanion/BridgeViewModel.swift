import Foundation

@MainActor
final class BridgeViewModel: ObservableObject {
    @Published var bridgeURL: String = "ws://127.0.0.1:9797/ws"
    @Published var token: String = ""
    @Published var events: [String] = []
    @Published var objective: String = ""

    private var socketTask: URLSessionWebSocketTask?

    func connect() {
        guard let url = URL(string: bridgeURL) else {
            events.insert("Invalid URL", at: 0)
            return
        }
        var request = URLRequest(url: url)
        if !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        socketTask = URLSession.shared.webSocketTask(with: request)
        socketTask?.resume()
        receiveLoop()
    }

    func disconnect() {
        socketTask?.cancel(with: .goingAway, reason: nil)
        socketTask = nil
    }

    func submitObjective() {
        guard !objective.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            events.insert("Objective is empty", at: 0)
            return
        }
        let payload: [String: Any] = [
            "type": "command",
            "id": UUID().uuidString,
            "method": "POST",
            "path": "/run_async",
            "body": ["objective": objective]
        ]
        sendJSON(payload)
    }

    private func sendJSON(_ value: [String: Any]) {
        guard let socketTask else {
            events.insert("Not connected", at: 0)
            return
        }
        do {
            let data = try JSONSerialization.data(withJSONObject: value)
            socketTask.send(.data(data)) { [weak self] error in
                Task { @MainActor in
                    if let error {
                        self?.events.insert("Send error: \(error.localizedDescription)", at: 0)
                    }
                }
            }
        } catch {
            events.insert("Encode error: \(error.localizedDescription)", at: 0)
        }
    }

    private func receiveLoop() {
        socketTask?.receive { [weak self] result in
            Task { @MainActor in
                switch result {
                case .failure(let error):
                    self?.events.insert("Receive error: \(error.localizedDescription)", at: 0)
                case .success(let message):
                    switch message {
                    case .string(let text):
                        self?.events.insert(text, at: 0)
                    case .data(let data):
                        let text = String(data: data, encoding: .utf8) ?? "<binary>"
                        self?.events.insert(text, at: 0)
                    @unknown default:
                        self?.events.insert("Unknown message", at: 0)
                    }
                    self?.receiveLoop()
                }
            }
        }
    }
}
