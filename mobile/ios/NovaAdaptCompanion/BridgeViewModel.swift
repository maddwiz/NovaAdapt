import Foundation

struct PlanSummary: Identifiable {
    let id: String
    let objective: String
    let status: String
    let strategy: String
    let actionCount: Int
    let progressCompleted: Int
    let progressTotal: Int
    let hasUndoActions: Bool
}

struct JobSummary: Identifiable {
    let id: String
    let status: String
    let kind: String
}

struct AuditEventSummary: Identifiable {
    let id: String
    let category: String
    let action: String
    let status: String
    let createdAt: String
}

struct TerminalSessionSummary: Identifiable {
    let id: String
    let open: Bool
    let command: String
    let cwd: String
    let lastSeq: Int
}

@MainActor
final class BridgeViewModel: ObservableObject {
    @Published var apiBaseURL: String = "http://127.0.0.1:9797"
    @Published var bridgeWSURL: String = "ws://127.0.0.1:9797/ws"
    @Published var token: String = ""
    @Published var objective: String = ""
    @Published var strategy: String = "single"
    @Published var candidatesCSV: String = ""
    @Published var execute: Bool = false
    @Published var plans: [PlanSummary] = []
    @Published var jobs: [JobSummary] = []
    @Published var events: [AuditEventSummary] = []
    @Published var wsEvents: [String] = []
    @Published var status: String = "Idle"

    @Published var terminalSessions: [TerminalSessionSummary] = []
    @Published var terminalSessionID: String = ""
    @Published var terminalCommand: String = ""
    @Published var terminalCWD: String = ""
    @Published var terminalShell: String = ""
    @Published var terminalInput: String = ""
    @Published var terminalOutput: String = ""
    @Published var terminalPollIntervalMs: Int = 250

    private var socketTask: URLSessionWebSocketTask?
    private var wsCommandResolvers: [String: (Result<[String: Any], Error>) -> Void] = [:]
    private var terminalPollTask: Task<Void, Never>?
    private var terminalNextSeq: Int = 0

    var pendingPlans: [PlanSummary] {
        plans.filter { $0.status.lowercased() == "pending" }
    }

    var activeJobs: [JobSummary] {
        jobs.filter {
            let normalized = $0.status.lowercased()
            return normalized == "running" || normalized == "queued"
        }
    }

    var websocketConnected: Bool {
        socketTask != nil
    }

    func connect() {
        guard let url = URL(string: bridgeWSURL) else {
            status = "Invalid WebSocket URL"
            return
        }
        var request = URLRequest(url: url)
        let bearer = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !bearer.isEmpty {
            request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        }
        disconnect()
        socketTask = URLSession.shared.webSocketTask(with: request)
        socketTask?.resume()
        status = "WebSocket connected"
        receiveLoop()
    }

    func disconnect() {
        socketTask?.cancel(with: .goingAway, reason: nil)
        socketTask = nil
        status = "WebSocket disconnected"
        stopTerminalPolling()
        resolveAllWSCommands(error: NSError(domain: "NovaAdaptCompanion", code: -1, userInfo: [NSLocalizedDescriptionKey: "WebSocket disconnected"]))
    }

    func refreshDashboard() {
        Task {
            await runAction(label: "Refreshing dashboard") {
                let payload = try await self.requestJSON(
                    method: "GET",
                    path: "/dashboard/data?plans_limit=30&jobs_limit=30&events_limit=30",
                    body: nil
                )
                self.plans = self.parsePlans(payload["plans"])
                self.jobs = self.parseJobs(payload["jobs"])
                self.events = self.parseEvents(payload["events"])
            }
        }
    }

    func queueObjective() {
        Task {
            guard !objective.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                status = "Objective is empty"
                return
            }
            await runAction(label: "Queueing objective") {
                _ = try await self.requestJSON(method: "POST", path: "/run_async", body: self.buildObjectivePayload())
                try await self.refreshDashboardAsync()
            }
        }
    }

    func createPlan() {
        Task {
            guard !objective.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                status = "Objective is empty"
                return
            }
            await runAction(label: "Creating plan") {
                _ = try await self.requestJSON(method: "POST", path: "/plans", body: self.buildObjectivePayload())
                try await self.refreshDashboardAsync()
            }
        }
    }

    func approvePlan(_ planId: String) {
        Task {
            await runAction(label: "Approving plan \(planId)") {
                _ = try await self.requestJSON(
                    method: "POST",
                    path: "/plans/\(planId)/approve",
                    body: ["execute": true]
                )
                try await self.refreshDashboardAsync()
            }
        }
    }

    func retryFailedPlan(_ planId: String) {
        Task {
            await runAction(label: "Queueing failed-step retry for \(planId)") {
                _ = try await self.requestJSON(
                    method: "POST",
                    path: "/plans/\(planId)/retry_failed_async",
                    body: [
                        "allow_dangerous": true,
                        "action_retry_attempts": 2,
                        "action_retry_backoff_seconds": 0.2,
                    ]
                )
                try await self.refreshDashboardAsync()
            }
        }
    }

    func rejectPlan(_ planId: String) {
        Task {
            await runAction(label: "Rejecting plan \(planId)") {
                _ = try await self.requestJSON(
                    method: "POST",
                    path: "/plans/\(planId)/reject",
                    body: ["reason": "Rejected from NovaAdapt iOS companion"]
                )
                try await self.refreshDashboardAsync()
            }
        }
    }

    func markUndoPlan(_ planId: String) {
        Task {
            await runAction(label: "Marking undo for \(planId)") {
                _ = try await self.requestJSON(
                    method: "POST",
                    path: "/plans/\(planId)/undo",
                    body: ["mark_only": true, "execute": false]
                )
                try await self.refreshDashboardAsync()
            }
        }
    }

    func cancelJob(_ jobId: String) {
        Task {
            await runAction(label: "Canceling job \(jobId)") {
                _ = try await self.requestJSON(method: "POST", path: "/jobs/\(jobId)/cancel", body: [:])
                try await self.refreshDashboardAsync()
            }
        }
    }

    func refreshTerminalSessions() {
        Task {
            do {
                let result = try await wsCommand(method: "GET", path: "/terminal/sessions", body: nil, idPrefix: "term-list", timeoutSeconds: 10)
                let payload = try parseCommandPayload(result)
                let rows = payload as? [[String: Any]] ?? []
                terminalSessions = parseTerminalSessions(rows)
                status = "Terminal sessions refreshed"
            } catch {
                status = "Terminal sessions refresh failed: \(error.localizedDescription)"
            }
        }
    }

    func startTerminalSession() {
        Task {
            do {
                var body: [String: Any] = ["max_chunks": 4000]
                let command = terminalCommand.trimmingCharacters(in: .whitespacesAndNewlines)
                if !command.isEmpty {
                    body["command"] = command
                }
                let cwd = terminalCWD.trimmingCharacters(in: .whitespacesAndNewlines)
                if !cwd.isEmpty {
                    body["cwd"] = cwd
                }
                let shell = terminalShell.trimmingCharacters(in: .whitespacesAndNewlines)
                if !shell.isEmpty {
                    body["shell"] = shell
                }

                let result = try await wsCommand(method: "POST", path: "/terminal/sessions", body: body, idPrefix: "term-start", timeoutSeconds: 15)
                guard let payload = try parseCommandPayload(result) as? [String: Any] else {
                    throw NSError(domain: "NovaAdaptCompanion", code: -2, userInfo: [NSLocalizedDescriptionKey: "terminal start payload invalid"])
                }
                let sessionID = string(payload["id"])
                guard !sessionID.isEmpty else {
                    throw NSError(domain: "NovaAdaptCompanion", code: -2, userInfo: [NSLocalizedDescriptionKey: "terminal start missing session id"])
                }

                attachTerminalSession(sessionID)
                refreshTerminalSessions()
                status = "Terminal session started"
            } catch {
                status = "Terminal start failed: \(error.localizedDescription)"
            }
        }
    }

    func attachTerminalSession(_ sessionID: String) {
        terminalSessionID = sessionID
        terminalNextSeq = 0
        terminalOutput = ""
        startTerminalPolling()
    }

    func closeTerminalSession() {
        Task {
            let id = terminalSessionID.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty else {
                status = "Terminal session id is empty"
                return
            }
            do {
                _ = try await wsCommand(
                    method: "POST",
                    path: "/terminal/sessions/\(id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id)/close",
                    body: [:],
                    idPrefix: "term-close",
                    timeoutSeconds: 10
                )
                stopTerminalPolling()
                terminalSessionID = ""
                terminalOutput = ""
                terminalNextSeq = 0
                refreshTerminalSessions()
                status = "Terminal session closed"
            } catch {
                status = "Terminal close failed: \(error.localizedDescription)"
            }
        }
    }

    func sendTerminalLine() {
        Task {
            guard !terminalSessionID.isEmpty else {
                status = "Attach or start a terminal session first"
                return
            }
            let line = terminalInput
            terminalInput = ""
            if line.isEmpty {
                return
            }
            do {
                _ = try await sendTerminalInput(line + "\n")
                status = "Terminal input sent"
            } catch {
                status = "Terminal input failed: \(error.localizedDescription)"
            }
        }
    }

    func sendTerminalCtrlC() {
        Task {
            guard !terminalSessionID.isEmpty else {
                status = "Attach or start a terminal session first"
                return
            }
            do {
                _ = try await sendTerminalInput("\u{0003}")
                status = "Ctrl+C sent"
            } catch {
                status = "Ctrl+C failed: \(error.localizedDescription)"
            }
        }
    }

    private func receiveLoop() {
        socketTask?.receive { [weak self] result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .failure(let error):
                    self.status = "WebSocket error: \(error.localizedDescription)"
                    self.resolveAllWSCommands(error: error)
                case .success(let message):
                    var text: String
                    switch message {
                    case .string(let raw):
                        text = raw
                    case .data(let data):
                        text = String(data: data, encoding: .utf8) ?? "<binary>"
                    @unknown default:
                        text = "Unknown WebSocket message"
                    }

                    let suppress = self.handleWSCommandResponse(text)
                    if !suppress {
                        self.wsEvents.insert(self.prettyJSON(text) ?? text, at: 0)
                        self.wsEvents = Array(self.wsEvents.prefix(60))
                    }
                    self.receiveLoop()
                }
            }
        }
    }

    private func handleWSCommandResponse(_ rawText: String) -> Bool {
        guard
            let data = rawText.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data),
            let payload = object as? [String: Any],
            let type = payload["type"] as? String,
            let id = payload["id"] as? String,
            !id.isEmpty
        else {
            return false
        }

        if type == "command_result" {
            resolveWSCommand(id: id, result: .success(payload))
            return id.hasPrefix("term-poll") || id.hasPrefix("term-input") || id.hasPrefix("term-list")
        }

        if type == "error" {
            let message = payload["error"] as? String ?? "command error"
            resolveWSCommand(
                id: id,
                result: .failure(
                    NSError(
                        domain: "NovaAdaptCompanion",
                        code: -1,
                        userInfo: [NSLocalizedDescriptionKey: message]
                    )
                )
            )
            return id.hasPrefix("term-poll") || id.hasPrefix("term-input") || id.hasPrefix("term-list")
        }

        if type == "ack" || type == "pong" {
            resolveWSCommand(id: id, result: .success(payload))
            return true
        }

        return false
    }

    private func runAction(label: String, operation: @escaping () async throws -> Void) async {
        status = "\(label)…"
        do {
            try await operation()
            status = "\(label) OK"
        } catch {
            status = "\(label) failed: \(error.localizedDescription)"
        }
    }

    private func refreshDashboardAsync() async throws {
        let payload = try await requestJSON(
            method: "GET",
            path: "/dashboard/data?plans_limit=30&jobs_limit=30&events_limit=30",
            body: nil
        )
        plans = parsePlans(payload["plans"])
        jobs = parseJobs(payload["jobs"])
        events = parseEvents(payload["events"])
    }

    private func startTerminalPolling() {
        stopTerminalPolling()
        let session = terminalSessionID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !session.isEmpty else {
            return
        }
        let pollInterval = max(75, min(2000, terminalPollIntervalMs))
        terminalPollTask = Task {
            while !Task.isCancelled {
                do {
                    try await pollTerminalOutputOnce(sessionID: session)
                } catch {
                    status = "Terminal poll failed: \(error.localizedDescription)"
                }
                try? await Task.sleep(nanoseconds: UInt64(pollInterval) * 1_000_000)
            }
        }
    }

    private func stopTerminalPolling() {
        terminalPollTask?.cancel()
        terminalPollTask = nil
    }

    private func pollTerminalOutputOnce(sessionID: String) async throws {
        guard !sessionID.isEmpty else {
            return
        }
        let encoded = sessionID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? sessionID
        let path = "/terminal/sessions/\(encoded)/output?since_seq=\(max(0, terminalNextSeq))&limit=500"
        let result = try await wsCommand(method: "GET", path: path, body: nil, idPrefix: "term-poll", timeoutSeconds: 12)
        guard let payload = try parseCommandPayload(result) as? [String: Any] else {
            throw NSError(domain: "NovaAdaptCompanion", code: -2, userInfo: [NSLocalizedDescriptionKey: "invalid terminal output payload"])
        }

        if let chunks = payload["chunks"] as? [[String: Any]], !chunks.isEmpty {
            for chunk in chunks {
                if let seq = toInt(chunk["seq"]), seq > terminalNextSeq {
                    terminalNextSeq = seq
                }
                if let data = chunk["data"] as? String, !data.isEmpty {
                    terminalOutput += data
                }
            }
            trimTerminalOutput()
        }

        if let nextSeq = toInt(payload["next_seq"]), nextSeq > terminalNextSeq {
            terminalNextSeq = nextSeq
        }
    }

    private func sendTerminalInput(_ input: String) async throws -> [String: Any] {
        let session = terminalSessionID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !session.isEmpty else {
            throw NSError(domain: "NovaAdaptCompanion", code: -2, userInfo: [NSLocalizedDescriptionKey: "terminal session id is empty"])
        }
        let encoded = session.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? session
        let result = try await wsCommand(
            method: "POST",
            path: "/terminal/sessions/\(encoded)/input",
            body: ["input": input],
            idPrefix: "term-input",
            timeoutSeconds: 8
        )
        guard let payload = try parseCommandPayload(result) as? [String: Any] else {
            throw NSError(domain: "NovaAdaptCompanion", code: -2, userInfo: [NSLocalizedDescriptionKey: "invalid terminal input payload"])
        }
        return payload
    }

    private func trimTerminalOutput() {
        let maxChars = 120_000
        guard terminalOutput.count > maxChars else {
            return
        }
        terminalOutput = String(terminalOutput.suffix(maxChars))
    }

    private func wsCommand(
        method: String,
        path: String,
        body: [String: Any]?,
        idPrefix: String,
        timeoutSeconds: Double
    ) async throws -> [String: Any] {
        guard socketTask != nil else {
            throw NSError(domain: "NovaAdaptCompanion", code: -1, userInfo: [NSLocalizedDescriptionKey: "WebSocket is not connected"])
        }

        let commandID = "\(idPrefix)-\(UUID().uuidString)"
        var payload: [String: Any] = [
            "type": "command",
            "id": commandID,
            "method": method.uppercased(),
            "path": path,
        ]
        if let body {
            payload["body"] = body
        }

        return try await withCheckedThrowingContinuation { continuation in
            wsCommandResolvers[commandID] = { result in
                continuation.resume(with: result)
            }

            Task {
                try? await Task.sleep(nanoseconds: UInt64(max(1.0, timeoutSeconds) * 1_000_000_000))
                await MainActor.run {
                    if let resolver = self.wsCommandResolvers.removeValue(forKey: commandID) {
                        resolver(
                            .failure(
                                NSError(
                                    domain: "NovaAdaptCompanion",
                                    code: -1,
                                    userInfo: [NSLocalizedDescriptionKey: "command timeout"]
                                )
                            )
                        )
                    }
                }
            }

            Task {
                do {
                    try await self.sendWebSocketJSON(payload)
                } catch {
                    await MainActor.run {
                        if let resolver = self.wsCommandResolvers.removeValue(forKey: commandID) {
                            resolver(.failure(error))
                        }
                    }
                }
            }
        }
    }

    private func parseCommandPayload(_ response: [String: Any]) throws -> Any {
        let statusCode = toInt(response["status"])
        let payload = response["payload"]
        if let statusCode, !(200 ... 299).contains(statusCode) {
            let message: String
            if let obj = payload as? [String: Any], let error = obj["error"] as? String {
                message = error
            } else {
                message = "command failed with status \(statusCode)"
            }
            throw NSError(domain: "NovaAdaptCompanion", code: statusCode, userInfo: [NSLocalizedDescriptionKey: message])
        }
        return payload as Any
    }

    private func sendWebSocketJSON(_ object: [String: Any]) async throws {
        guard let socketTask else {
            throw NSError(domain: "NovaAdaptCompanion", code: -1, userInfo: [NSLocalizedDescriptionKey: "WebSocket is not connected"])
        }
        let data = try JSONSerialization.data(withJSONObject: object)
        guard let text = String(data: data, encoding: .utf8) else {
            throw NSError(domain: "NovaAdaptCompanion", code: -1, userInfo: [NSLocalizedDescriptionKey: "Failed to encode websocket payload"])
        }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            socketTask.send(.string(text)) { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume(returning: ())
                }
            }
        }
    }

    private func resolveWSCommand(id: String, result: Result<[String: Any], Error>) {
        guard let resolver = wsCommandResolvers.removeValue(forKey: id) else {
            return
        }
        resolver(result)
    }

    private func resolveAllWSCommands(error: Error) {
        let callbacks = wsCommandResolvers.values
        wsCommandResolvers.removeAll()
        for callback in callbacks {
            callback(.failure(error))
        }
    }

    private func buildObjectivePayload() -> [String: Any] {
        var payload: [String: Any] = [
            "objective": objective.trimmingCharacters(in: .whitespacesAndNewlines),
            "strategy": strategy,
            "execute": execute,
            "metadata": [
                "source": "ios-companion",
                "created_at": ISO8601DateFormatter().string(from: Date()),
            ],
        ]
        let candidates = candidatesCSV
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if strategy == "vote", !candidates.isEmpty {
            payload["candidates"] = candidates
        }
        return payload
    }

    private func requestJSON(
        method: String,
        path: String,
        body: [String: Any]?
    ) async throws -> [String: Any] {
        guard let url = makeURL(path: path) else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = method.uppercased()
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let bearer = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !bearer.isEmpty {
            request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        let parsed = parseJSONObject(data) ?? [:]
        guard (200 ... 299).contains(http.statusCode) else {
            let message = parsed["error"] as? String ?? String(data: data, encoding: .utf8) ?? "request failed"
            throw NSError(
                domain: "NovaAdaptCompanion",
                code: http.statusCode,
                userInfo: [NSLocalizedDescriptionKey: message]
            )
        }
        return parsed
    }

    private func makeURL(path: String) -> URL? {
        let base = apiBaseURL
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !base.isEmpty else {
            return nil
        }
        if path.hasPrefix("/") {
            return URL(string: base + path)
        }
        return URL(string: base + "/" + path)
    }

    private func parseJSONObject(_ data: Data) -> [String: Any]? {
        guard !data.isEmpty else {
            return [:]
        }
        guard let raw = try? JSONSerialization.jsonObject(with: data) else {
            return nil
        }
        return raw as? [String: Any]
    }

    private func parsePlans(_ value: Any?) -> [PlanSummary] {
        guard let items = value as? [[String: Any]] else {
            return []
        }
        let parsed = items.map { item -> PlanSummary in
            let id = string(item["id"])
            let actionLogIDs = (item["action_log_ids"] as? [Any]) ?? []
            return PlanSummary(
                id: id.isEmpty ? UUID().uuidString : id,
                objective: string(item["objective"]),
                status: string(item["status"], fallback: "unknown"),
                strategy: string(item["strategy"], fallback: "single"),
                actionCount: int(item["actions"], fallback: 0, treatArrayAsCount: true),
                progressCompleted: int(item["progress_completed"], fallback: 0, treatArrayAsCount: false),
                progressTotal: int(item["progress_total"], fallback: 0, treatArrayAsCount: false),
                hasUndoActions: !actionLogIDs.isEmpty
            )
        }
        return parsed.sorted { lhs, rhs in
            planRank(lhs.status) < planRank(rhs.status)
        }
    }

    private func parseJobs(_ value: Any?) -> [JobSummary] {
        guard let items = value as? [[String: Any]] else {
            return []
        }
        let parsed = items.map { item in
            JobSummary(
                id: string(item["id"], fallback: UUID().uuidString),
                status: string(item["status"], fallback: "unknown"),
                kind: string(item["kind"], fallback: "run")
            )
        }
        return parsed.sorted { lhs, rhs in
            jobRank(lhs.status) < jobRank(rhs.status)
        }
    }

    private func parseEvents(_ value: Any?) -> [AuditEventSummary] {
        guard let items = value as? [[String: Any]] else {
            return []
        }
        return items.prefix(30).map { item in
            AuditEventSummary(
                id: string(item["id"], fallback: UUID().uuidString),
                category: string(item["category"], fallback: "event"),
                action: string(item["action"]),
                status: string(item["status"], fallback: "unknown"),
                createdAt: string(item["created_at"], fallback: "-")
            )
        }
    }

    private func parseTerminalSessions(_ rows: [[String: Any]]) -> [TerminalSessionSummary] {
        rows.map { row in
            let commandItems = (row["command"] as? [Any]) ?? []
            let command = commandItems
                .compactMap { item -> String? in
                    if let text = item as? String {
                        return text
                    }
                    if let number = item as? NSNumber {
                        return number.stringValue
                    }
                    return nil
                }
                .joined(separator: " ")
            return TerminalSessionSummary(
                id: string(row["id"], fallback: UUID().uuidString),
                open: (row["open"] as? Bool) ?? false,
                command: command,
                cwd: string(row["cwd"]),
                lastSeq: toInt(row["last_seq"]) ?? 0
            )
        }
        .sorted { lhs, rhs in
            lhs.id < rhs.id
        }
    }

    private func string(_ value: Any?, fallback: String = "") -> String {
        switch value {
        case let text as String:
            return text
        case let number as NSNumber:
            return number.stringValue
        default:
            return fallback
        }
    }

    private func int(_ value: Any?, fallback: Int, treatArrayAsCount: Bool) -> Int {
        if treatArrayAsCount, let items = value as? [Any] {
            return items.count
        }
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let text = value as? String, let parsed = Int(text) {
            return parsed
        }
        return fallback
    }

    private func toInt(_ value: Any?) -> Int? {
        if let number = value as? NSNumber {
            return number.intValue
        }
        if let text = value as? String {
            return Int(text)
        }
        return nil
    }

    private func planRank(_ status: String) -> Int {
        switch status.lowercased() {
        case "pending": return 0
        case "executing": return 1
        case "approved": return 2
        case "failed": return 3
        case "executed": return 4
        case "rejected": return 5
        default: return 99
        }
    }

    private func jobRank(_ status: String) -> Int {
        switch status.lowercased() {
        case "running": return 0
        case "queued": return 1
        case "failed": return 2
        case "succeeded": return 3
        case "canceled": return 4
        default: return 99
        }
    }

    private func prettyJSON(_ raw: String) -> String? {
        guard let data = raw.data(using: .utf8) else {
            return nil
        }
        guard let object = try? JSONSerialization.jsonObject(with: data) else {
            return nil
        }
        guard let pretty = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted]) else {
            return nil
        }
        return String(data: pretty, encoding: .utf8)
    }
}
