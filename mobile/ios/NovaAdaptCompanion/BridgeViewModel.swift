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
    let executionError: String
    let repairedCount: Int
    let repairSummary: String
    let collaborationSummary: String
    let transcriptPreview: [String]
}

struct JobSummary: Identifiable {
    let id: String
    let status: String
    let kind: String
    let objective: String
    let error: String
    let resultSummary: String
    let repairSummary: String
    let collaborationSummary: String
    let transcriptPreview: [String]
}

struct AuditEventSummary: Identifiable {
    let id: String
    let category: String
    let action: String
    let status: String
    let createdAt: String
}

struct ControlArtifactSummary: Identifiable {
    let id: String
    let controlType: String
    let status: String
    let platform: String
    let transport: String
    let goal: String
    let outputPreview: String
    let actionType: String
    let target: String
    let model: String
    let createdAt: String
    let previewPath: String
    let dangerous: Bool
}

struct HomeAssistantEntitySummary: Identifiable {
    let id: String
    let entityID: String
    let domain: String
    let friendlyName: String
    let state: String
    let detail: String
}

struct MQTTMessageSummary: Identifiable {
    let id: String
    let topic: String
    let payload: String
    let qos: Int
    let retain: Bool
    let receivedAt: String
}

struct RuntimeGovernanceModelSummary: Identifiable {
    let id: String
    let label: String
    let modelID: String
    let calls: Int
    let estimatedCostUSD: Double
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
    @Published var autoRepairAttempts: Int = 0 {
        didSet { persistSettings() }
    }
    @Published var repairStrategy: String = "decompose" {
        didSet { persistSettings() }
    }
    @Published var repairModel: String = "" {
        didSet { persistSettings() }
    }
    @Published var repairCandidatesCSV: String = "" {
        didSet { persistSettings() }
    }
    @Published var repairFallbacksCSV: String = "" {
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
    @Published var controlArtifacts: [ControlArtifactSummary] = []
    @Published var iotDomainFilter: String = "" {
        didSet { persistSettings() }
    }
    @Published var iotEntityPrefix: String = "" {
        didSet { persistSettings() }
    }
    @Published var homeAssistantEntities: [HomeAssistantEntitySummary] = []
    @Published var mqttTopic: String = "" {
        didSet { persistSettings() }
    }
    @Published var mqttPayload: String = "" {
        didSet { persistSettings() }
    }
    @Published var mqttRetain: Bool = false {
        didSet { persistSettings() }
    }
    @Published var mqttMessages: [MQTTMessageSummary] = []
    @Published var mqttStatusSummary: String = "MQTT idle"
    @Published var governancePaused: Bool = false
    @Published var governancePauseReason: String = ""
    @Published var governanceBudgetLimit: String = "" {
        didSet { persistSettings() }
    }
    @Published var governanceMaxActiveRuns: String = "" {
        didSet { persistSettings() }
    }
    @Published var governanceActiveRuns: Int = 0
    @Published var governanceRunsTotal: Int = 0
    @Published var governanceLLMCallsTotal: Int = 0
    @Published var governanceSpendEstimateUSD: Double = 0
    @Published var governanceUpdatedAt: String = ""
    @Published var governanceLastRunAt: String = ""
    @Published var governanceLastObjectivePreview: String = ""
    @Published var governanceLastStrategy: String = ""
    @Published var governanceJobActive: Int = 0
    @Published var governanceJobQueued: Int = 0
    @Published var governanceJobRunning: Int = 0
    @Published var governanceJobMaxWorkers: Int = 0
    @Published var governancePerModel: [RuntimeGovernanceModelSummary] = []
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
        static let autoRepairAttempts = "novaadapt.mobile.autoRepairAttempts"
        static let repairStrategy = "novaadapt.mobile.repairStrategy"
        static let repairModel = "novaadapt.mobile.repairModel"
        static let repairCandidatesCSV = "novaadapt.mobile.repairCandidatesCSV"
        static let repairFallbacksCSV = "novaadapt.mobile.repairFallbacksCSV"
        static let sessionScopesCSV = "novaadapt.mobile.sessionScopesCSV"
        static let sessionTTLSeconds = "novaadapt.mobile.sessionTTLSeconds"
        static let issuedSessionID = "novaadapt.mobile.issuedSessionID"
        static let revokeExpiresAt = "novaadapt.mobile.revokeExpiresAt"
        static let allowlistDeviceID = "novaadapt.mobile.allowlistDeviceID"
        static let iotDomainFilter = "novaadapt.mobile.iotDomainFilter"
        static let iotEntityPrefix = "novaadapt.mobile.iotEntityPrefix"
        static let mqttTopic = "novaadapt.mobile.mqttTopic"
        static let mqttPayload = "novaadapt.mobile.mqttPayload"
        static let mqttRetain = "novaadapt.mobile.mqttRetain"
        static let governanceBudgetLimit = "novaadapt.mobile.governanceBudgetLimit"
        static let governanceMaxActiveRuns = "novaadapt.mobile.governanceMaxActiveRuns"
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
                self.controlArtifacts = self.parseControlArtifacts(payload["control_artifacts"])
                self.applyRuntimeGovernancePayload(payload["governance"])
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
                    body: self.buildRepairPayload(base: ["execute": true])
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
                    body: self.buildRepairPayload(base: [
                        "allow_dangerous": true,
                        "action_retry_attempts": 2,
                        "action_retry_backoff_seconds": 0.2,
                    ])
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

    func refreshIoTEntities() {
        Task {
            await runAction(label: "Refreshing IoT entities") {
                try await self.refreshIoTEntitiesAsync()
            }
        }
    }

    func refreshMQTTStatus() {
        Task {
            await runAction(label: "Refreshing MQTT status") {
                let payload = try await self.requestJSON(method: "GET", path: "/iot/mqtt/status", body: nil)
                self.mqttStatusSummary = self.formatMQTTStatus(payload)
            }
        }
    }

    func refreshRuntimeGovernance() {
        Task {
            await runAction(label: "Refreshing runtime governance") {
                let payload = try await self.requestJSON(method: "GET", path: "/runtime/governance", body: nil)
                self.applyRuntimeGovernancePayload(payload)
            }
        }
    }

    func applyRuntimeGovernance() {
        Task {
            await runAction(label: "Applying runtime governance") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/runtime/governance",
                    body: self.buildRuntimeGovernanceUpdatePayload()
                )
                self.applyRuntimeGovernancePayload(payload)
                try await self.refreshDashboardAsync()
            }
        }
    }

    func pauseRuntime() {
        Task {
            await runAction(label: "Pausing runtime") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/runtime/governance",
                    body: [
                        "paused": true,
                        "pause_reason": "Paused from NovaAdapt iOS companion",
                    ]
                )
                self.applyRuntimeGovernancePayload(payload)
                try await self.refreshDashboardAsync()
            }
        }
    }

    func resumeRuntime() {
        Task {
            await runAction(label: "Resuming runtime") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/runtime/governance",
                    body: [
                        "paused": false,
                        "pause_reason": "",
                    ]
                )
                self.applyRuntimeGovernancePayload(payload)
                try await self.refreshDashboardAsync()
            }
        }
    }

    func resetRuntimeUsage() {
        Task {
            await runAction(label: "Resetting runtime usage") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/runtime/governance",
                    body: ["reset_usage": true]
                )
                self.applyRuntimeGovernancePayload(payload)
                try await self.refreshDashboardAsync()
            }
        }
    }

    func cancelAllJobs() {
        Task {
            await runAction(label: "Canceling all jobs") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/runtime/jobs/cancel_all",
                    body: [
                        "pause": true,
                        "pause_reason": "Cancel all from NovaAdapt iOS companion",
                    ]
                )
                self.applyRuntimeGovernancePayload(payload["governance"])
                try await self.refreshDashboardAsync()
            }
        }
    }

    func executeHomeAssistantService(entityID: String, domain: String, service: String) {
        Task {
            await runAction(label: "Executing \(domain).\(service)") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/iot/homeassistant/action",
                    body: [
                        "action": [
                            "type": "ha_service",
                            "domain": domain,
                            "service": service,
                            "entity_id": entityID,
                        ],
                        "execute": true,
                    ]
                )
                self.mqttStatusSummary = self.string(payload["output"], fallback: "\(domain).\(service) sent")
                try await self.refreshDashboardAsync()
                try await self.refreshIoTEntitiesAsync()
            }
        }
    }

    func publishMQTTMessage() {
        Task {
            let topic = mqttTopic.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !topic.isEmpty else {
                status = "MQTT topic is empty"
                return
            }
            await runAction(label: "Publishing MQTT message") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/iot/mqtt/publish",
                    body: [
                        "topic": topic,
                        "payload": self.mqttPayload,
                        "retain": self.mqttRetain,
                        "execute": true,
                    ]
                )
                self.mqttStatusSummary = self.string(payload["output"], fallback: "MQTT publish complete")
                try await self.refreshDashboardAsync()
                try await self.refreshMQTTStatusAsync()
            }
        }
    }

    func subscribeMQTTSnapshot() {
        Task {
            let topic = mqttTopic.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !topic.isEmpty else {
                status = "MQTT topic is empty"
                return
            }
            await runAction(label: "Subscribing to MQTT snapshot") {
                let payload = try await self.requestJSON(
                    method: "POST",
                    path: "/iot/mqtt/subscribe",
                    body: [
                        "topic": topic,
                        "timeout_seconds": 1.5,
                        "max_messages": 6,
                        "qos": 0,
                    ]
                )
                let data = payload["data"] as? [String: Any]
                self.mqttMessages = self.parseMQTTMessages(data?["messages"])
                self.mqttStatusSummary = self.string(payload["output"], fallback: "MQTT snapshot complete")
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
        let autoRepair = defaults.integer(forKey: DefaultsKey.autoRepairAttempts)
        if autoRepair > 0 {
            autoRepairAttempts = max(0, min(10, autoRepair))
        }
        if let value = defaults.string(forKey: DefaultsKey.repairStrategy), !value.isEmpty {
            repairStrategy = value
        }
        if let value = defaults.string(forKey: DefaultsKey.repairModel) {
            repairModel = value
        }
        if let value = defaults.string(forKey: DefaultsKey.repairCandidatesCSV) {
            repairCandidatesCSV = value
        }
        if let value = defaults.string(forKey: DefaultsKey.repairFallbacksCSV) {
            repairFallbacksCSV = value
        }
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
        if let value = defaults.string(forKey: DefaultsKey.iotDomainFilter) {
            iotDomainFilter = value
        }
        if let value = defaults.string(forKey: DefaultsKey.iotEntityPrefix) {
            iotEntityPrefix = value
        }
        if let value = defaults.string(forKey: DefaultsKey.mqttTopic) {
            mqttTopic = value
        }
        if let value = defaults.string(forKey: DefaultsKey.mqttPayload) {
            mqttPayload = value
        }
        mqttRetain = defaults.bool(forKey: DefaultsKey.mqttRetain)
        if let value = defaults.string(forKey: DefaultsKey.governanceBudgetLimit) {
            governanceBudgetLimit = value
        }
        if let value = defaults.string(forKey: DefaultsKey.governanceMaxActiveRuns) {
            governanceMaxActiveRuns = value
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
        defaults.set(max(0, min(10, autoRepairAttempts)), forKey: DefaultsKey.autoRepairAttempts)
        defaults.set(repairStrategy, forKey: DefaultsKey.repairStrategy)
        defaults.set(repairModel, forKey: DefaultsKey.repairModel)
        defaults.set(repairCandidatesCSV, forKey: DefaultsKey.repairCandidatesCSV)
        defaults.set(repairFallbacksCSV, forKey: DefaultsKey.repairFallbacksCSV)
        defaults.set(sessionScopesCSV, forKey: DefaultsKey.sessionScopesCSV)
        defaults.set(max(60, min(86400, sessionTTLSeconds)), forKey: DefaultsKey.sessionTTLSeconds)
        defaults.set(issuedSessionID, forKey: DefaultsKey.issuedSessionID)
        defaults.set(revokeExpiresAt, forKey: DefaultsKey.revokeExpiresAt)
        defaults.set(allowlistDeviceID, forKey: DefaultsKey.allowlistDeviceID)
        defaults.set(iotDomainFilter, forKey: DefaultsKey.iotDomainFilter)
        defaults.set(iotEntityPrefix, forKey: DefaultsKey.iotEntityPrefix)
        defaults.set(mqttTopic, forKey: DefaultsKey.mqttTopic)
        defaults.set(mqttPayload, forKey: DefaultsKey.mqttPayload)
        defaults.set(mqttRetain, forKey: DefaultsKey.mqttRetain)
        defaults.set(governanceBudgetLimit, forKey: DefaultsKey.governanceBudgetLimit)
        defaults.set(governanceMaxActiveRuns, forKey: DefaultsKey.governanceMaxActiveRuns)
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
        controlArtifacts = parseControlArtifacts(payload["control_artifacts"])
        applyRuntimeGovernancePayload(payload["governance"])
    }

    private func refreshIoTEntitiesAsync() async throws {
        let domain = iotDomainFilter.trimmingCharacters(in: .whitespacesAndNewlines)
        let prefix = iotEntityPrefix.trimmingCharacters(in: .whitespacesAndNewlines)
        var queryItems = [URLQueryItem(name: "limit", value: "24")]
        if !domain.isEmpty {
            queryItems.append(URLQueryItem(name: "domain", value: domain))
        }
        if !prefix.isEmpty {
            queryItems.append(URLQueryItem(name: "entity_id_prefix", value: prefix))
        }
        var components = URLComponents()
        components.queryItems = queryItems
        let query = components.percentEncodedQuery ?? "limit=24"
        let payload = try await requestJSON(
            method: "GET",
            path: "/iot/homeassistant/entities?\(query)",
            body: nil
        )
        homeAssistantEntities = parseHomeAssistantEntities(payload)
    }

    private func refreshMQTTStatusAsync() async throws {
        let payload = try await requestJSON(method: "GET", path: "/iot/mqtt/status", body: nil)
        mqttStatusSummary = formatMQTTStatus(payload)
    }

    private func buildRuntimeGovernanceUpdatePayload() -> [String: Any] {
        var payload: [String: Any] = [:]
        let budget = governanceBudgetLimit.trimmingCharacters(in: .whitespacesAndNewlines)
        if budget.isEmpty {
            payload["budget_limit_usd"] = NSNull()
        } else if let value = Double(budget) {
            payload["budget_limit_usd"] = value
        }

        let maxRuns = governanceMaxActiveRuns.trimmingCharacters(in: .whitespacesAndNewlines)
        if maxRuns.isEmpty {
            payload["max_active_runs"] = NSNull()
        } else if let value = Int(maxRuns) {
            payload["max_active_runs"] = max(1, value)
        }
        return payload
    }

    private func applyRuntimeGovernancePayload(_ value: Any?) {
        guard let payload = value as? [String: Any] else {
            return
        }

        governancePaused = bool(payload["paused"])
        governancePauseReason = string(payload["pause_reason"])
        governanceBudgetLimit = string(payload["budget_limit_usd"])
        governanceMaxActiveRuns = string(payload["max_active_runs"])
        governanceActiveRuns = toInt(payload["active_runs"]) ?? 0
        governanceRunsTotal = toInt(payload["runs_total"]) ?? 0
        governanceLLMCallsTotal = toInt(payload["llm_calls_total"]) ?? 0
        governanceSpendEstimateUSD = toDouble(payload["spend_estimate_usd"]) ?? 0
        governanceUpdatedAt = string(payload["updated_at"])
        governanceLastRunAt = string(payload["last_run_at"])
        governanceLastObjectivePreview = string(payload["last_objective_preview"])
        governanceLastStrategy = string(payload["last_strategy"], fallback: "single")

        let jobs = payload["jobs"] as? [String: Any] ?? [:]
        governanceJobActive = toInt(jobs["active"]) ?? 0
        governanceJobQueued = toInt(jobs["queued"]) ?? 0
        governanceJobRunning = toInt(jobs["running"]) ?? 0
        governanceJobMaxWorkers = toInt(jobs["max_workers"]) ?? 0
        governancePerModel = parseRuntimeGovernanceModels(payload["per_model"])
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
        if !candidates.isEmpty {
            payload["candidates"] = candidates
        }
        return buildRepairPayload(base: payload)
    }

    private func buildRepairPayload(base: [String: Any]) -> [String: Any] {
        var payload = base
        let attempts = max(0, min(10, autoRepairAttempts))
        if attempts > 0 {
            payload["auto_repair_attempts"] = attempts
        }
        let normalizedRepairStrategy = repairStrategy.trimmingCharacters(in: .whitespacesAndNewlines)
        if !normalizedRepairStrategy.isEmpty {
            payload["repair_strategy"] = normalizedRepairStrategy
        }
        let normalizedRepairModel = repairModel.trimmingCharacters(in: .whitespacesAndNewlines)
        if !normalizedRepairModel.isEmpty {
            payload["repair_model"] = normalizedRepairModel
        }
        let repairCandidates = repairCandidatesCSV
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if !repairCandidates.isEmpty {
            payload["repair_candidates"] = repairCandidates
        }
        let repairFallbacks = repairFallbacksCSV
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if !repairFallbacks.isEmpty {
            payload["repair_fallbacks"] = repairFallbacks
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
            let executionResults = (item["execution_results"] as? [[String: Any]]) ?? []
            let repairedCount = executionResults.filter {
                string($0["status"]).lowercased() == "repaired"
            }.count
            return PlanSummary(
                id: id.isEmpty ? UUID().uuidString : id,
                objective: string(item["objective"]),
                status: string(item["status"], fallback: "unknown"),
                strategy: string(item["strategy"], fallback: "single"),
                actionCount: int(item["actions"], fallback: 0, treatArrayAsCount: true),
                progressCompleted: int(item["progress_completed"], fallback: 0, treatArrayAsCount: false),
                progressTotal: int(item["progress_total"], fallback: 0, treatArrayAsCount: false),
                hasUndoActions: !actionLogIDs.isEmpty,
                executionError: string(item["execution_error"]),
                repairedCount: repairedCount,
                repairSummary: summarizeRepair(item["repair"], executionResults: executionResults),
                collaborationSummary: summarizeCollaboration(
                    voteSummary: item["vote_summary"],
                    collaboration: item["collaboration"],
                    fallbackStrategy: string(item["strategy"], fallback: "single")
                ),
                transcriptPreview: transcriptPreviewLines(item["collaboration"])
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
        let parsed = items.map { item -> JobSummary in
            let result = item["result"] as? [String: Any]
            let metadata = item["metadata"] as? [String: Any]
            let kind = string(item["kind"], fallback: string(metadata?["kind"], fallback: "run"))
            return JobSummary(
                id: string(item["id"], fallback: UUID().uuidString),
                status: string(item["status"], fallback: "unknown"),
                kind: kind.isEmpty ? "run" : kind,
                objective: string(item["objective"], fallback: string(metadata?["objective"])),
                error: string(item["error"]),
                resultSummary: summarizeJobResult(result),
                repairSummary: summarizeRepair(result?["repair"], executionResults: (result?["results"] as? [[String: Any]]) ?? []),
                collaborationSummary: summarizeCollaboration(
                    voteSummary: result?["vote_summary"],
                    collaboration: result?["collaboration"],
                    fallbackStrategy: string(result?["strategy"], fallback: kind)
                ),
                transcriptPreview: transcriptPreviewLines(result?["collaboration"])
            )
        }
        return parsed.sorted { lhs, rhs in
            jobRank(lhs.status) < jobRank(rhs.status)
        }
    }

    private func summarizeRepair(_ value: Any?, executionResults: [[String: Any]]) -> String {
        let repairedCount = executionResults.filter {
            string($0["status"]).lowercased() == "repaired"
        }.count
        guard let repair = value as? [String: Any] else {
            return repairedCount > 0 ? "\(repairedCount) repaired action\(repairedCount == 1 ? "" : "s")" : ""
        }
        let healed = bool(repair["healed"])
        let attempts = toInt(repair["attempts"]) ?? 0
        let unresolved = ((repair["failed_indexes"] as? [Any]) ?? []).count
        let lastError = string(repair["last_error"])
        var parts: [String] = []
        if healed {
            parts.append("auto-repair healed")
        } else if attempts > 0 {
            parts.append("auto-repair attempted")
        }
        if repairedCount > 0 {
            parts.append("\(repairedCount) repaired")
        }
        if attempts > 0 {
            parts.append("\(attempts) attempt\(attempts == 1 ? "" : "s")")
        }
        if unresolved > 0 && !healed {
            parts.append("\(unresolved) unresolved")
        }
        if !lastError.isEmpty && !healed {
            parts.append(lastError)
        }
        return parts.joined(separator: " • ")
    }

    private func summarizeCollaboration(voteSummary: Any?, collaboration: Any?, fallbackStrategy: String) -> String {
        let vote = voteSummary as? [String: Any] ?? [:]
        let collab = collaboration as? [String: Any] ?? [:]
        let mode = string(collab["mode"], fallback: fallbackStrategy).lowercased()
        if toInt(vote["subtasks_total"]) != nil || mode == "decompose" {
            let total = toInt(vote["subtasks_total"]) ?? 0
            let succeeded = toInt(vote["subtasks_succeeded"]) ?? 0
            let reviewed = toInt(vote["reviewed_subtasks"]) ?? 0
            let batches = toInt(vote["parallel_batches"]) ?? 0
            var parts = ["decompose"]
            if total > 0 {
                parts.append("\(succeeded)/\(total) subtasks")
            }
            if reviewed > 0 {
                parts.append("\(reviewed) reviewed")
            }
            if batches > 0 {
                parts.append("\(batches) batches")
            }
            let reason = string(vote["reason"])
            if !reason.isEmpty {
                parts.append(reason.replacingOccurrences(of: "_", with: " "))
            }
            return parts.joined(separator: " • ")
        }
        if toInt(vote["winner_votes"]) != nil || mode == "vote" {
            let winnerVotes = toInt(vote["winner_votes"]) ?? 0
            let totalVotes = toInt(vote["total_votes"]) ?? 0
            var parts = ["vote"]
            if totalVotes > 0 {
                parts.append("\(winnerVotes)/\(totalVotes) votes")
            }
            if bool(vote["quorum_met"]) {
                parts.append("quorum")
            }
            return parts.joined(separator: " • ")
        }
        return ""
    }

    private func transcriptPreviewLines(_ value: Any?, limit: Int = 3) -> [String] {
        guard
            let collaboration = value as? [String: Any],
            let transcript = collaboration["transcript"] as? [[String: Any]]
        else {
            return []
        }
        return transcript.compactMap { item in
            let type = string(item["type"]).lowercased()
            switch type {
            case "subtask_started":
                let subtaskID = string(item["subtask_id"], fallback: "subtask")
                let model = string(item["model"])
                return "started \(subtaskID)\(model.isEmpty ? "" : " with \(model)")"
            case "subtask_output":
                let subtaskID = string(item["subtask_id"], fallback: "subtask")
                let model = string(item["model"])
                let attempt = toInt(item["attempt"]) ?? 1
                return "output \(subtaskID) • \(model) • attempt \(attempt)"
            case "subtask_review":
                let subtaskID = string(item["subtask_id"], fallback: "subtask")
                let reviewer = string(item["reviewer_model"], fallback: "reviewer")
                let approved = bool(item["approved"])
                return "\(reviewer) \(approved ? "approved" : "rejected") \(subtaskID)"
            case "subtask_failed":
                let subtaskID = string(item["subtask_id"], fallback: "subtask")
                let error = string(item["error"], fallback: "failed")
                return "\(subtaskID) failed • \(error)"
            case "synthesis":
                let model = string(item["model"], fallback: "model")
                return "synthesis by \(model)"
            default:
                return nil
            }
        }
        .prefix(limit)
        .map { $0 }
    }

    private func summarizeJobResult(_ value: [String: Any]?) -> String {
        guard let payload = value else {
            return ""
        }
        let model = string(payload["model"])
        let strategy = string(payload["strategy"])
        let results = (payload["results"] as? [[String: Any]]) ?? []
        var statusCounts: [String: Int] = [:]
        for item in results {
            let status = string(item["status"], fallback: "unknown").lowercased()
            statusCounts[status, default: 0] += 1
        }
        var parts: [String] = []
        if !strategy.isEmpty {
            parts.append(strategy)
        }
        if !model.isEmpty {
            parts.append(model)
        }
        if !results.isEmpty {
            let ok = statusCounts["ok"] ?? 0
            let preview = statusCounts["preview"] ?? 0
            let repaired = statusCounts["repaired"] ?? 0
            let failed = (statusCounts["failed"] ?? 0) + (statusCounts["blocked"] ?? 0)
            parts.append("\(results.count) actions")
            if ok > 0 { parts.append("\(ok) ok") }
            if preview > 0 { parts.append("\(preview) preview") }
            if repaired > 0 { parts.append("\(repaired) repaired") }
            if failed > 0 { parts.append("\(failed) failed") }
        }
        return parts.joined(separator: " • ")
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

    private func parseControlArtifacts(_ value: Any?) -> [ControlArtifactSummary] {
        guard let items = value as? [[String: Any]] else {
            return []
        }
        return items.prefix(12).map { item in
            let id = string(item["artifact_id"], fallback: UUID().uuidString)
            let dangerous = (item["dangerous"] as? Bool)
                ?? ((item["dangerous"] as? NSNumber)?.boolValue ?? false)
            return ControlArtifactSummary(
                id: id,
                controlType: string(item["control_type"], fallback: "control"),
                status: string(item["status"], fallback: "unknown"),
                platform: string(item["platform"]),
                transport: string(item["transport"]),
                goal: string(item["goal"]),
                outputPreview: string(item["output_preview"]),
                actionType: string(item["action_type"]),
                target: string(item["target"]),
                model: string(item["model"]),
                createdAt: string(item["created_at"], fallback: "-"),
                previewPath: string(item["preview_path"]),
                dangerous: dangerous
            )
        }
    }

    private func parseHomeAssistantEntities(_ payload: [String: Any]) -> [HomeAssistantEntitySummary] {
        guard let items = payload["entities"] as? [[String: Any]] else {
            return []
        }
        return items.map { item in
            let entityID = string(item["entity_id"], fallback: UUID().uuidString)
            let attributes = item["attributes"] as? [String: Any] ?? [:]
            let domain = entityID.split(separator: ".", maxSplits: 1).first.map(String.init) ?? ""
            let friendlyName = string(attributes["friendly_name"], fallback: entityID)
            return HomeAssistantEntitySummary(
                id: entityID,
                entityID: entityID,
                domain: domain,
                friendlyName: friendlyName.isEmpty ? entityID : friendlyName,
                state: string(item["state"], fallback: "unknown"),
                detail: summarizeHomeAssistantAttributes(attributes)
            )
        }
        .sorted { lhs, rhs in
            lhs.friendlyName.localizedCaseInsensitiveCompare(rhs.friendlyName) == .orderedAscending
        }
    }

    private func parseMQTTMessages(_ value: Any?) -> [MQTTMessageSummary] {
        guard let items = value as? [[String: Any]] else {
            return []
        }
        return items.map { item in
            MQTTMessageSummary(
                id: UUID().uuidString,
                topic: string(item["topic"]),
                payload: string(item["payload"]),
                qos: toInt(item["qos"]) ?? 0,
                retain: bool(item["retain"]),
                receivedAt: formatReceivedAt(item["received_at"])
            )
        }
    }

    private func parseRuntimeGovernanceModels(_ value: Any?) -> [RuntimeGovernanceModelSummary] {
        guard let items = value as? [String: Any] else {
            return []
        }
        return items.compactMap { key, raw in
            guard let payload = raw as? [String: Any] else {
                return nil
            }
            let label = key.trimmingCharacters(in: .whitespacesAndNewlines)
            let modelID = string(payload["model_id"])
            return RuntimeGovernanceModelSummary(
                id: label.isEmpty ? UUID().uuidString : label,
                label: label.isEmpty ? "model" : label,
                modelID: modelID,
                calls: toInt(payload["calls"]) ?? 0,
                estimatedCostUSD: toDouble(payload["estimated_cost_usd"]) ?? 0
            )
        }
        .sorted { lhs, rhs in
            if lhs.calls != rhs.calls {
                return lhs.calls > rhs.calls
            }
            return lhs.label.localizedCaseInsensitiveCompare(rhs.label) == .orderedAscending
        }
    }

    func controlArtifactPreviewURL(for artifact: ControlArtifactSummary) -> URL? {
        let rawPath = artifact.previewPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rawPath.isEmpty else {
            return nil
        }
        guard let base = normalizedAPIBaseURL() else {
            return nil
        }
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            return nil
        }
        components.path = rawPath.hasPrefix("/") ? rawPath : "/" + rawPath
        let bearer = token.trimmingCharacters(in: .whitespacesAndNewlines)
        if !bearer.isEmpty {
            components.queryItems = (components.queryItems ?? []) + [URLQueryItem(name: "token", value: bearer)]
        }
        return components.url
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

    private func toDouble(_ value: Any?) -> Double? {
        if let number = value as? NSNumber {
            return number.doubleValue
        }
        if let text = value as? String {
            return Double(text)
        }
        return nil
    }

    private func bool(_ value: Any?) -> Bool {
        if let flag = value as? Bool {
            return flag
        }
        if let number = value as? NSNumber {
            return number.boolValue
        }
        if let text = value as? String {
            return ["1", "true", "yes", "on"].contains(text.lowercased())
        }
        return false
    }

    private func summarizeHomeAssistantAttributes(_ attributes: [String: Any]) -> String {
        var parts: [String] = []
        for key in ["device_class", "unit_of_measurement", "brightness", "temperature", "current_position"] {
            let value = attributes[key]
            let text = string(value)
            if !text.isEmpty {
                parts.append("\(key): \(text)")
            }
            if parts.count >= 4 {
                break
            }
        }
        return parts.isEmpty ? "No additional attributes" : parts.joined(separator: " • ")
    }

    private func formatMQTTStatus(_ payload: [String: Any]) -> String {
        let ok = bool(payload["ok"])
        let host = string(payload["host"], fallback: string(payload["broker"], fallback: "broker"))
        let port = string(payload["port"])
        let configured = bool(payload["configured"])
        if ok {
            return "MQTT connected to \(host)\(port.isEmpty ? "" : ":\(port)")"
        }
        if !configured {
            return "MQTT not configured"
        }
        let errorText = string(payload["error"])
        return errorText.isEmpty ? "MQTT unavailable" : "MQTT unavailable: \(errorText)"
    }

    private func formatReceivedAt(_ value: Any?) -> String {
        if let number = value as? NSNumber {
            return Self.timestampFormatter.string(from: Date(timeIntervalSince1970: number.doubleValue))
        }
        if let text = value as? String, let parsed = Double(text) {
            return Self.timestampFormatter.string(from: Date(timeIntervalSince1970: parsed))
        }
        return "-"
    }

    private static let timestampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .medium
        return formatter
    }()

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
