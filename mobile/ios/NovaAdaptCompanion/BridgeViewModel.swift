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

    private var socketTask: URLSessionWebSocketTask?

    var pendingPlans: [PlanSummary] {
        plans.filter { $0.status.lowercased() == "pending" }
    }

    var activeJobs: [JobSummary] {
        jobs.filter {
            let normalized = $0.status.lowercased()
            return normalized == "running" || normalized == "queued"
        }
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
        socketTask?.cancel(with: .goingAway, reason: nil)
        socketTask = URLSession.shared.webSocketTask(with: request)
        socketTask?.resume()
        status = "WebSocket connected"
        receiveLoop()
    }

    func disconnect() {
        socketTask?.cancel(with: .goingAway, reason: nil)
        socketTask = nil
        status = "WebSocket disconnected"
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

    private func receiveLoop() {
        socketTask?.receive { [weak self] result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .failure(let error):
                    self.status = "WebSocket error: \(error.localizedDescription)"
                case .success(let message):
                    switch message {
                    case .string(let text):
                        self.wsEvents.insert(self.prettyJSON(text) ?? text, at: 0)
                    case .data(let data):
                        let text = String(data: data, encoding: .utf8) ?? "<binary>"
                        self.wsEvents.insert(self.prettyJSON(text) ?? text, at: 0)
                    @unknown default:
                        self.wsEvents.insert("Unknown WebSocket message", at: 0)
                    }
                    self.wsEvents = Array(self.wsEvents.prefix(60))
                    self.receiveLoop()
                }
            }
        }
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
        let base = apiBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
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
