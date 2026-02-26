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
    @Published var apiBaseURL: String = "http://127.0.0.1:9797" {
        didSet { persistSettings() }
    }
    @Published var bridgeWSURL: String = "ws://127.0.0.1:9797/ws" {
        didSet { persistSettings() }
    }
    @Published var token: String = "" {
        didSet { persistSecrets() }
    }
    @Published var adminToken: String = "" {
        didSet { persistSecrets() }
    }
    @Published var bridgeDeviceID: String = "" {
        didSet { persistSettings() }
    }
    @Published var objective: String = "" {
        didSet { persistSettings() }
    }
    @Published var strategy: String = "single" {
        didSet { persistSettings() }
    }
    @Published var candidatesCSV: String = "" {
        didSet { persistSettings() }
    }
    @Published var execute: Bool = false {
        didSet { persistSettings() }
    }
    @Published var sessionScopesCSV: String = "read,run,plan,approve,reject,undo,cancel" {
        didSet { persistSettings() }
    }
    @Published var sessionTTLSeconds: Int = 900 {
        didSet { persistSettings() }
    }
    @Published var issuedSessionID: String = "" {
        didSet { persistSettings() }
    }
    @Published var revokeExpiresAt: String = "" {
        didSet { persistSettings() }
    }
    @Published var allowlistDeviceID: String = "" {
        didSet { persistSettings() }
    }
    @Published var allowlistSummary: String = "unknown"
    @Published var plans: [PlanSummary] = []
    @Published var jobs: [JobSummary] = []
    @Published var events: [AuditEventSummary] = []
    @Published var wsEvents: [String] = []
    @Published var status: String = "Idle"

    @Published var terminalSessions: [TerminalSessionSummary] = []
    @Published var terminalSessionID: String = ""
    @Published var terminalCommand: String = "" {
        didSet { persistSettings() }
    }
    @Published var terminalCWD: String = "" {
        didSet { persistSettings() }
    }
    @Published var terminalShell: String = "" {
        didSet { persistSettings() }
    }
    @Published var terminalInput: String = ""
    @Published var terminalOutput: String = ""
    @Published var terminalPollIntervalMs: Int = 250 {
        didSet { persistSettings() }
    }

    private var socketTask: URLSessionWebSocketTask?
    private var wsCommandResolvers: [String: (Result<[String: Any], Error>) -> Void] = [:]
    private var terminalPollTask: Task<Void, Never>?
    private var terminalNextSeq: Int = 0
    private var hydrating = false

    private enum DefaultsKey {
        static let apiBaseURL = "novaadapt.mobile.apiBaseURL"
        static let bridgeWSURL = "novaadapt.mobile.bridgeWSURL"
        static let bridgeDeviceID = "novaadapt.mobile.bridgeDeviceID"
        static let objective = "novaadapt.mobile.objective"
        static let strategy = "novaadapt.mobile.strategy"
        static let candidatesCSV = "novaadapt.mobile.candidatesCSV"
        static let execute = "novaadapt.mobile.execute"
        static let sessionScopesCSV = "novaadapt.mobile.sessionScopesCSV"
        static let sessionTTLSeconds = "novaadapt.mobile.sessionTTLSeconds"
        static let issuedSessionID = "novaadapt.mobile.issuedSessionID"
        static let revokeExpiresAt = "novaadapt.mobile.revokeExpiresAt"
        static let allowlistDeviceID = "novaadapt.mobile.allowlistDeviceID"
        static let terminalCommand = "novaadapt.mobile.terminalCommand"
        static let terminalCWD = "novaadapt.mobile.terminalCWD"
        static let terminalShell = "novaadapt.mobile.terminalShell"
        static let terminalPollIntervalMs = "novaadapt.mobile.terminalPollIntervalMs"
    }

    private enum SecretKey {
        static let token = "operatorToken"
        static let adminToken = "adminToken"
    }

    init() {
        hydratePersistedState()
    }

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
        guard let url = normalizedWebSocketURL() else {
            status = "Invalid WebSocket URL (ws/wss required)"
            return
        }
        var request = URLRequest(url: url)
        let bearer = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !bearer.isEmpty {
            request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        }
        let deviceID = bridgeDeviceID.trimmingCharacters(in: .whitespacesAndNewlines)
        if !deviceID.isEmpty {
            request.setValue(deviceID, forHTTPHeaderField: "X-Device-ID")
        }
        disconnect()
        socketTask = URLSession.shared.webSocketTask(with: request)
        socketTask?.resume()
        status = "WebSocket connected"
        receiveLoop()
    }

    func testConnection() {
        Task {
            await runAction(label: "Testing core connection") {
                _ = try await self.requestJSON(method: "GET", path: "/health", body: nil)
            }
        }
    }

    func clearStoredCredentials() {
        token = ""
        adminToken = ""
        status = "Stored credentials cleared"
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

    func refreshAllowedDevices() {
        Task {
            let adminBearer = adminOrPrimaryToken()
            guard !adminBearer.isEmpty else {
                status = "Admin token is empty"
                return
            }
            await runAction(label: "Refreshing allowlist") {
                let payload = try await self.requestJSON(
                    method: "GET",
                    path: "/auth/devices",
                    body: nil,
                    tokenOverride: adminBearer
                )
                self.applyAllowedDevices(payload)
            }
        }
    }

    func issueSessionToken() {
        Task {
            let adminBearer = adminOrPrimaryToken()
            guard !adminBearer.isEmpty else {
                status = "Admin token is empty"
                return
            }
            let scopes = sessionScopesCSV
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            guard !scopes.isEmpty else {
                status = "Session scopes are empty"
                return
            }
            let ttl = max(60, min(86400, sessionTTLSeconds))
            await runAction(label: "Issuing session token") {
                var body: [String: Any] = [
                    "scopes": scopes,
                    "ttl_seconds": ttl,
                ]
                let deviceID = self.bridgeDeviceID.trimmingCharacters(in: .whitespacesAndNewlines)
                if !deviceID.isEmpty {
                    body["device_id"] = deviceID
                }
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/auth/session",
                    body: body,
                    tokenOverride: adminBearer
                )
                let issuedToken = self.string(payload["token"])
                guard !issuedToken.isEmpty else {
                    throw NSError(domain: "NovaAdaptCompanion", code: -2, userInfo: [NSLocalizedDescriptionKey: "session token missing in response"])
                }
                self.token = issuedToken
                self.issuedSessionID = self.string(payload["session_id"])
            }
        }
    }

    func revokeSessionToken() {
        Task {
            let adminBearer = adminOrPrimaryToken()
            guard !adminBearer.isEmpty else {
                status = "Admin token is empty"
                return
            }
            let tokenToRevoke = token.trimmingCharacters(in: .whitespacesAndNewlines)
            let sessionID = issuedSessionID.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !tokenToRevoke.isEmpty || !sessionID.isEmpty else {
                status = "Session token or session id is required"
                return
            }

            await runAction(label: "Revoking session token") {
                var body: [String: Any] = [:]
                if !tokenToRevoke.isEmpty {
                    body["token"] = tokenToRevoke
                }
                if !sessionID.isEmpty {
                    body["session_id"] = sessionID
                }
                let expiresAt = Int(self.revokeExpiresAt.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
                if expiresAt > 0 {
                    body["expires_at"] = expiresAt
                }
                _ = try await self.requestJSON(
                    method: "POST",
                    path: "/auth/session/revoke",
                    body: body,
                    tokenOverride: adminBearer
                )
            }
        }
    }

    func addAllowedDevice() {
        Task {
            let adminBearer = adminOrPrimaryToken()
            guard !adminBearer.isEmpty else {
                status = "Admin token is empty"
                return
            }
            let deviceID = allowlistDeviceID.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !deviceID.isEmpty else {
                status = "Allowlist device id is empty"
                return
            }
            await runAction(label: "Adding allowlisted device \(deviceID)") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/auth/devices",
                    body: ["device_id": deviceID],
                    tokenOverride: adminBearer
                )
                self.applyAllowedDevices(payload)
            }
        }
    }

    func removeAllowedDevice() {
        Task {
            let adminBearer = adminOrPrimaryToken()
            guard !adminBearer.isEmpty else {
                status = "Admin token is empty"
                return
            }
            let deviceID = allowlistDeviceID.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !deviceID.isEmpty else {
                status = "Allowlist device id is empty"
                return
            }
            await runAction(label: "Removing allowlisted device \(deviceID)") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/auth/devices/remove",
                    body: ["device_id": deviceID],
                    tokenOverride: adminBearer
                )
                self.applyAllowedDevices(payload)
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

    private func hydratePersistedState() {
        hydrating = true
        defer { hydrating = false }

        let defaults = UserDefaults.standard
        if let value = defaults.string(forKey: DefaultsKey.apiBaseURL), !value.isEmpty {
            apiBaseURL = value
        }
        if let value = defaults.string(forKey: DefaultsKey.bridgeWSURL), !value.isEmpty {
            bridgeWSURL = value
        }
        if let value = defaults.string(forKey: DefaultsKey.bridgeDeviceID) {
            bridgeDeviceID = value
        }
        if let value = defaults.string(forKey: DefaultsKey.objective) {
            objective = value
        }
        if let value = defaults.string(forKey: DefaultsKey.strategy), !value.isEmpty {
            strategy = value
        }
        if let value = defaults.string(forKey: DefaultsKey.candidatesCSV) {
            candidatesCSV = value
        }
        execute = defaults.bool(forKey: DefaultsKey.execute)
        if let value = defaults.string(forKey: DefaultsKey.sessionScopesCSV), !value.isEmpty {
            sessionScopesCSV = value
        }
        let ttl = defaults.integer(forKey: DefaultsKey.sessionTTLSeconds)
        if ttl > 0 {
            sessionTTLSeconds = max(60, min(86400, ttl))
        }
        if let value = defaults.string(forKey: DefaultsKey.issuedSessionID) {
            issuedSessionID = value
        }
        if let value = defaults.string(forKey: DefaultsKey.revokeExpiresAt) {
            revokeExpiresAt = value
        }
        if let value = defaults.string(forKey: DefaultsKey.allowlistDeviceID) {
            allowlistDeviceID = value
        }
        if let value = defaults.string(forKey: DefaultsKey.terminalCommand) {
            terminalCommand = value
        }
        if let value = defaults.string(forKey: DefaultsKey.terminalCWD) {
            terminalCWD = value
        }
        if let value = defaults.string(forKey: DefaultsKey.terminalShell) {
            terminalShell = value
        }
        let pollMs = defaults.integer(forKey: DefaultsKey.terminalPollIntervalMs)
        if pollMs > 0 {
            terminalPollIntervalMs = max(75, min(2000, pollMs))
        }

        token = KeychainStore.get(SecretKey.token) ?? ""
        adminToken = KeychainStore.get(SecretKey.adminToken) ?? ""
    }

    private func persistSettings() {
        if hydrating {
            return
        }
        let defaults = UserDefaults.standard
        defaults.set(apiBaseURL, forKey: DefaultsKey.apiBaseURL)
        defaults.set(bridgeWSURL, forKey: DefaultsKey.bridgeWSURL)
        defaults.set(bridgeDeviceID, forKey: DefaultsKey.bridgeDeviceID)
        defaults.set(objective, forKey: DefaultsKey.objective)
        defaults.set(strategy, forKey: DefaultsKey.strategy)
        defaults.set(candidatesCSV, forKey: DefaultsKey.candidatesCSV)
        defaults.set(execute, forKey: DefaultsKey.execute)
        defaults.set(sessionScopesCSV, forKey: DefaultsKey.sessionScopesCSV)
        defaults.set(max(60, min(86400, sessionTTLSeconds)), forKey: DefaultsKey.sessionTTLSeconds)
        defaults.set(issuedSessionID, forKey: DefaultsKey.issuedSessionID)
        defaults.set(revokeExpiresAt, forKey: DefaultsKey.revokeExpiresAt)
        defaults.set(allowlistDeviceID, forKey: DefaultsKey.allowlistDeviceID)
        defaults.set(terminalCommand, forKey: DefaultsKey.terminalCommand)
        defaults.set(terminalCWD, forKey: DefaultsKey.terminalCWD)
        defaults.set(terminalShell, forKey: DefaultsKey.terminalShell)
        defaults.set(max(75, min(2000, terminalPollIntervalMs)), forKey: DefaultsKey.terminalPollIntervalMs)
    }

    private func persistSecrets() {
        if hydrating {
            return
        }
        let operatorToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if operatorToken.isEmpty {
            KeychainStore.delete(SecretKey.token)
        } else {
            KeychainStore.set(operatorToken, for: SecretKey.token)
        }

        let adminBearer = adminToken.trimmingCharacters(in: .whitespacesAndNewlines)
        if adminBearer.isEmpty {
            KeychainStore.delete(SecretKey.adminToken)
        } else {
            KeychainStore.set(adminBearer, for: SecretKey.adminToken)
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

    private func adminOrPrimaryToken() -> String {
        let admin = adminToken.trimmingCharacters(in: .whitespacesAndNewlines)
        if !admin.isEmpty {
            return admin
        }
        return token.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func requestJSON(
        method: String,
        path: String,
        body: [String: Any]?,
        tokenOverride: String? = nil
    ) async throws -> [String: Any] {
        guard let url = makeURL(path: path) else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = method.uppercased()
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let bearer = (tokenOverride ?? token).trimmingCharacters(in: .whitespacesAndNewlines)
        if !bearer.isEmpty {
            request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        }
        let deviceID = bridgeDeviceID.trimmingCharacters(in: .whitespacesAndNewlines)
        if !deviceID.isEmpty {
            request.setValue(deviceID, forHTTPHeaderField: "X-Device-ID")
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
        guard let base = normalizedAPIBaseURL() else {
            return nil
        }
        let baseText = base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let normalizedPath = path.hasPrefix("/") ? path : "/\(path)"
        return URL(string: baseText + normalizedPath)
    }

    private func normalizedAPIBaseURL() -> URL? {
        let raw = apiBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty, let parsed = URL(string: raw), let scheme = parsed.scheme?.lowercased() else {
            return nil
        }
        guard scheme == "http" || scheme == "https" else {
            return nil
        }
        guard parsed.host != nil else {
            return nil
        }
        var components = URLComponents(url: parsed, resolvingAgainstBaseURL: false)
        components?.query = nil
        components?.fragment = nil
        return components?.url
    }

    private func normalizedWebSocketURL() -> URL? {
        let raw = bridgeWSURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !raw.isEmpty, let parsed = URL(string: raw), let scheme = parsed.scheme?.lowercased() else {
            return nil
        }
        guard scheme == "ws" || scheme == "wss" else {
            return nil
        }
        guard parsed.host != nil else {
            return nil
        }
        var components = URLComponents(url: parsed, resolvingAgainstBaseURL: false)
        components?.fragment = nil
        return components?.url
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

    private func applyAllowedDevices(_ payload: [String: Any]) {
        let devices = parseStringArray(payload["devices"])
        let count = toInt(payload["count"]) ?? devices.count
        if devices.isEmpty {
            allowlistSummary = "\(count) device(s)"
        } else {
            allowlistSummary = "\(count) device(s): \(devices.joined(separator: ", "))"
        }
    }

    private func parseStringArray(_ value: Any?) -> [String] {
        guard let values = value as? [Any] else {
            return []
        }
        return values
            .compactMap { item -> String? in
                let text = string(item).trimmingCharacters(in: .whitespacesAndNewlines)
                return text.isEmpty ? nil : text
            }
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
