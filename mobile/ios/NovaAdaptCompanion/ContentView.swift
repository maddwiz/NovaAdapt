import SwiftUI
import UIKit

struct ContentView: View {
    @EnvironmentObject private var bridge: BridgeViewModel
    @State private var pendingConfirmation: PendingConfirmation?

    var body: some View {
        NavigationStack {
            ZStack {
                backgroundView
                    .ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        heroCard
                        statusCard
                        connectionCard
                        objectiveCard
                        plansCard
                        jobsCard
                        terminalCard
                        eventsCard
                        websocketCard
                    }
                    .padding(16)
                }
            }
            .navigationTitle("NovaAdapt")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Refresh") {
                        bridge.refreshDashboard()
                    }
                }
            }
            .preferredColorScheme(.dark)
            .onAppear {
                bridge.refreshDashboard()
            }
            .confirmationDialog(
                confirmationTitle,
                isPresented: Binding(
                    get: { pendingConfirmation != nil },
                    set: { shouldShow in
                        if !shouldShow {
                            pendingConfirmation = nil
                        }
                    }
                ),
                titleVisibility: .visible
            ) {
                Button("Confirm", role: .destructive) {
                    executePendingConfirmation()
                }
                Button("Cancel", role: .cancel) {
                    pendingConfirmation = nil
                }
            } message: {
                Text(confirmationMessage)
            }
        }
    }

    private var backgroundView: some View {
        ZStack {
            LinearGradient(
                colors: [.novaBgDeep, .novaBgMid, .novaBgBottom],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            RadialGradient(
                colors: [.novaBrand.opacity(0.28), .clear],
                center: .topLeading,
                startRadius: 40,
                endRadius: 360
            )

            RadialGradient(
                colors: [.novaHot.opacity(0.32), .clear],
                center: .trailing,
                startRadius: 20,
                endRadius: 320
            )

            RadialGradient(
                colors: [.novaIndigo.opacity(0.24), .clear],
                center: .bottom,
                startRadius: 60,
                endRadius: 330
            )
        }
    }

    private var heroCard: some View {
        ZStack(alignment: .topTrailing) {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [Color(red: 23 / 255, green: 15 / 255, blue: 57 / 255, opacity: 0.9),
                                 Color(red: 10 / 255, green: 9 / 255, blue: 29 / 255, opacity: 0.92),
                                 Color(red: 38 / 255, green: 8 / 255, blue: 44 / 255, opacity: 0.9)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.novaLineStrong, lineWidth: 1)
                )

            VStack(alignment: .leading, spacing: 8) {
                Text("NovaAI Theme")
                    .font(.caption.weight(.bold))
                    .kerning(1.6)
                    .textCase(.uppercase)
                    .foregroundStyle(Color.novaBrand)

                Text("NovaAdapt Control Plane")
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .foregroundStyle(Color.white)

                Text("Any app. Any model. Anywhere.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaInk.opacity(0.92))
                    .lineLimit(2)

                HStack {
                    Spacer(minLength: 0)
                    logoView
                }
            }
            .padding(16)
        }
        .shadow(color: .black.opacity(0.45), radius: 24, y: 14)
    }

    private var logoView: some View {
        Group {
            if let uiImage = UIImage(named: "novaai-logo-user") {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(
                            LinearGradient(colors: [.novaIndigo, .novaHot], startPoint: .topLeading, endPoint: .bottomTrailing)
                        )
                    Text("Nova_AI")
                        .font(.headline)
                        .foregroundStyle(.white)
                }
            }
        }
        .frame(width: 132, height: 96)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.novaHot.opacity(0.7), lineWidth: 1)
        )
        .shadow(color: .novaBrand.opacity(0.32), radius: 16, y: 6)
    }

    private var statusCard: some View {
        sectionCard(title: "Status") {
            Text(bridge.status)
                .font(.subheadline)
                .foregroundStyle(Color.novaInk)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var connectionCard: some View {
        sectionCard(title: "Connection") {
            TextField("Bridge/Core API URL", text: $bridge.apiBaseURL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            TextField("Bridge WebSocket URL", text: $bridge.bridgeWSURL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            SecureField("Token", text: $bridge.token)
                .textFieldStyle(.roundedBorder)

            SecureField("Admin Token (optional)", text: $bridge.adminToken)
                .textFieldStyle(.roundedBorder)

            TextField("Device ID (for allowlisted bridge)", text: $bridge.bridgeDeviceID)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            TextField("Session Scopes (CSV)", text: $bridge.sessionScopesCSV)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            Stepper("Session TTL: \(bridge.sessionTTLSeconds)s", value: $bridge.sessionTTLSeconds, in: 60 ... 86400, step: 60)
                .foregroundStyle(Color.novaInk)

            TextField("Issued Session ID", text: $bridge.issuedSessionID)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            TextField("Revoke Expires At (unix, optional)", text: $bridge.revokeExpiresAt)
                .keyboardType(.numberPad)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Issue Session") { bridge.issueSessionToken() }
                    .buttonStyle(.bordered)
                    .tint(.novaBrand)
                Button("Revoke Session") { pendingConfirmation = .revokeSession }
                    .buttonStyle(.bordered)
                    .tint(.novaDanger)
            }

            TextField("Allowlist Device ID", text: $bridge.allowlistDeviceID)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            Text("Allowlist: \(bridge.allowlistSummary)")
                .font(.caption)
                .foregroundStyle(Color.novaMuted)

            HStack {
                Button("List Devices") { bridge.refreshAllowedDevices() }
                    .buttonStyle(.bordered)
                Button("Add Device") { bridge.addAllowedDevice() }
                    .buttonStyle(.bordered)
                Button("Remove Device") { pendingConfirmation = .removeAllowlistedDevice }
                    .buttonStyle(.bordered)
                    .tint(.novaDanger)
            }

            HStack {
                Button("Refresh Dashboard") { bridge.refreshDashboard() }
                    .buttonStyle(.borderedProminent)
                    .tint(.novaBrand)
                Button("Test Connection") { bridge.testConnection() }
                    .buttonStyle(.bordered)
                Button("Clear Tokens") { bridge.clearStoredCredentials() }
                    .buttonStyle(.bordered)
                    .tint(.novaDanger)
                Spacer(minLength: 8)
                Button("Connect WS") { bridge.connect() }
                    .buttonStyle(.bordered)
                    .tint(.novaGood)
                Button("Disconnect") { bridge.disconnect() }
                    .buttonStyle(.bordered)
            }
        }
    }

    private var objectiveCard: some View {
        sectionCard(title: "Objective Console") {
            TextField("Objective", text: $bridge.objective)
                .textFieldStyle(.roundedBorder)

            Picker("Strategy", selection: $bridge.strategy) {
                Text("single").tag("single")
                Text("vote").tag("vote")
            }
            .pickerStyle(.segmented)

            TextField("Vote candidates (CSV)", text: $bridge.candidatesCSV)
                .textFieldStyle(.roundedBorder)

            Toggle("Execute actions immediately", isOn: $bridge.execute)
                .foregroundStyle(Color.novaInk)
                .tint(.novaHot)

            HStack {
                Button("Queue Async Run") { bridge.queueObjective() }
                    .buttonStyle(.borderedProminent)
                    .tint(.novaBrand)
                Button("Create Plan") { bridge.createPlan() }
                    .buttonStyle(.bordered)
            }
        }
    }

    private var plansCard: some View {
        sectionCard(title: "Plans (\(bridge.pendingPlans.count) pending)") {
            if bridge.plans.isEmpty {
                Text("No plans loaded.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                ForEach(Array(bridge.plans.prefix(12))) { plan in
                    itemCard {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(plan.objective.isEmpty ? "(no objective)" : plan.objective)
                                .font(.headline)
                                .foregroundStyle(.white)
                            Text("id: \(plan.id)")
                                .font(.caption.monospaced())
                                .foregroundStyle(Color.novaMuted)
                            Text("status: \(plan.status) • strategy: \(plan.strategy) • actions: \(plan.actionCount) • progress: \(plan.progressCompleted)/\(plan.progressTotal)")
                                .font(.caption)
                                .foregroundStyle(Color.novaMuted)
                            HStack {
                                if plan.status.lowercased() == "pending" {
                                    Button("Approve + Execute") { pendingConfirmation = .approvePlan(plan.id) }
                                        .buttonStyle(.borderedProminent)
                                        .tint(.novaBrand)
                                    Button("Reject") { pendingConfirmation = .rejectPlan(plan.id) }
                                        .buttonStyle(.bordered)
                                        .tint(.novaDanger)
                                }
                                if plan.status.lowercased() == "failed" {
                                    Button("Retry Failed Steps") { pendingConfirmation = .retryFailed(plan.id) }
                                        .buttonStyle(.borderedProminent)
                                        .tint(.novaGood)
                                }
                                if plan.hasUndoActions {
                                    Button("Undo (Mark)") { bridge.markUndoPlan(plan.id) }
                                        .buttonStyle(.bordered)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private var jobsCard: some View {
        sectionCard(title: "Jobs (\(bridge.activeJobs.count) active)") {
            if bridge.jobs.isEmpty {
                Text("No jobs loaded.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                ForEach(Array(bridge.jobs.prefix(12))) { job in
                    itemCard {
                        HStack(alignment: .top, spacing: 10) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(job.kind)
                                    .font(.headline)
                                    .foregroundStyle(.white)
                                Text("id: \(job.id)")
                                    .font(.caption.monospaced())
                                    .foregroundStyle(Color.novaMuted)
                                Text("status: \(job.status)")
                                    .font(.caption)
                                    .foregroundStyle(Color.novaMuted)
                            }
                            Spacer()
                            if job.status.lowercased() == "running" || job.status.lowercased() == "queued" {
                                Button("Cancel") { pendingConfirmation = .cancelJob(job.id) }
                                    .buttonStyle(.bordered)
                                    .tint(.novaDanger)
                            }
                        }
                    }
                }
            }
        }
    }

    private var terminalCard: some View {
        sectionCard(title: "Terminal") {
            TextField("Session ID", text: $bridge.terminalSessionID)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Refresh Sessions") { bridge.refreshTerminalSessions() }
                    .buttonStyle(.bordered)
                if !bridge.terminalSessions.isEmpty {
                    Picker("Attach", selection: $bridge.terminalSessionID) {
                        Text("Select").tag("")
                        ForEach(bridge.terminalSessions) { session in
                            Text("\(session.id)\(session.open ? "" : " (closed)")")
                                .tag(session.id)
                        }
                    }
                    .pickerStyle(.menu)
                }
            }

            TextField("Startup command (optional)", text: $bridge.terminalCommand)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            TextField("Working directory (optional)", text: $bridge.terminalCWD)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            TextField("Shell (optional)", text: $bridge.terminalShell)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            Stepper("Poll interval: \(bridge.terminalPollIntervalMs)ms", value: $bridge.terminalPollIntervalMs, in: 75 ... 2000, step: 25)
                .foregroundStyle(Color.novaInk)

            HStack {
                Button("Start Session") { bridge.startTerminalSession() }
                    .buttonStyle(.borderedProminent)
                    .tint(.novaBrand)
                Button("Attach Session") {
                    if !bridge.terminalSessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        bridge.attachTerminalSession(bridge.terminalSessionID)
                    }
                }
                .buttonStyle(.bordered)
                Button("Close") { bridge.closeTerminalSession() }
                    .buttonStyle(.bordered)
                    .tint(.novaDanger)
            }

            HStack {
                TextField("Type command", text: $bridge.terminalInput)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { bridge.sendTerminalLine() }
                    .buttonStyle(.borderedProminent)
                    .tint(.novaBrand)
                Button("Ctrl+C") { bridge.sendTerminalCtrlC() }
                    .buttonStyle(.bordered)
                    .tint(.novaDanger)
            }

            if bridge.terminalOutput.isEmpty {
                Text("No terminal output yet.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                Text(bridge.terminalOutput)
                    .font(.caption.monospaced())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color.black.opacity(0.85))
                    .foregroundStyle(Color.green.opacity(0.95))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke(Color.novaLine.opacity(0.85), lineWidth: 1)
                    )
            }
        }
    }

    private var eventsCard: some View {
        sectionCard(title: "Audit Events") {
            if bridge.events.isEmpty {
                Text("No events loaded.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                ForEach(Array(bridge.events.prefix(12))) { event in
                    itemCard {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(event.category) / \(event.action)")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(.white)
                            Text("status: \(event.status) • \(event.createdAt)")
                                .font(.caption)
                                .foregroundStyle(Color.novaMuted)
                        }
                    }
                }
            }
        }
    }

    private var websocketCard: some View {
        sectionCard(title: "WebSocket Feed") {
            if bridge.wsEvents.isEmpty {
                Text("No websocket events yet.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                ForEach(Array(bridge.wsEvents.prefix(20)), id: \.self) { item in
                    itemCard {
                        Text(item)
                            .font(.caption.monospaced())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .foregroundStyle(Color.novaInk)
                    }
                }
            }
        }
    }

    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .kerning(1.2)
                .textCase(.uppercase)
                .foregroundStyle(Color.novaBrand)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.novaPanel)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.novaLine, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.3), radius: 12, y: 8)
    }

    private func itemCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(Color.novaPanelStrong)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color.novaLine.opacity(0.85), lineWidth: 1)
            )
    }
}

private enum PendingConfirmation {
    case revokeSession
    case removeAllowlistedDevice
    case approvePlan(String)
    case rejectPlan(String)
    case retryFailed(String)
    case cancelJob(String)
}

private extension ContentView {
    var confirmationTitle: String {
        guard let pendingConfirmation else { return "Confirm action" }
        switch pendingConfirmation {
        case .revokeSession:
            return "Revoke session token?"
        case .removeAllowlistedDevice:
            return "Remove allowlisted device?"
        case .approvePlan:
            return "Approve and execute this plan?"
        case .rejectPlan:
            return "Reject this plan?"
        case .retryFailed:
            return "Retry failed plan steps?"
        case .cancelJob:
            return "Cancel this running job?"
        }
    }

    var confirmationMessage: String {
        guard let pendingConfirmation else { return "" }
        switch pendingConfirmation {
        case .revokeSession:
            return "This revokes active session credentials issued from the bridge."
        case .removeAllowlistedDevice:
            return "This removes the selected device from trusted bridge access."
        case .approvePlan(let id):
            return "Plan \(id) will be executed immediately."
        case .rejectPlan(let id):
            return "Plan \(id) will be marked rejected."
        case .retryFailed(let id):
            return "Only failed steps for plan \(id) will be queued for retry."
        case .cancelJob(let id):
            return "Job \(id) will be canceled."
        }
    }

    func executePendingConfirmation() {
        guard let pendingConfirmation else { return }
        defer { self.pendingConfirmation = nil }
        switch pendingConfirmation {
        case .revokeSession:
            bridge.revokeSessionToken()
        case .removeAllowlistedDevice:
            bridge.removeAllowedDevice()
        case .approvePlan(let id):
            bridge.approvePlan(id)
        case .rejectPlan(let id):
            bridge.rejectPlan(id)
        case .retryFailed(let id):
            bridge.retryFailedPlan(id)
        case .cancelJob(let id):
            bridge.cancelJob(id)
        }
    }
}

private extension Color {
    static let novaBgDeep = Color(red: 4 / 255, green: 2 / 255, blue: 13 / 255)
    static let novaBgMid = Color(red: 14 / 255, green: 7 / 255, blue: 34 / 255)
    static let novaBgBottom = Color(red: 5 / 255, green: 3 / 255, blue: 20 / 255)
    static let novaPanel = Color(red: 14 / 255, green: 11 / 255, blue: 33 / 255, opacity: 0.83)
    static let novaPanelStrong = Color(red: 10 / 255, green: 8 / 255, blue: 24 / 255, opacity: 0.93)
    static let novaInk = Color(red: 235 / 255, green: 236 / 255, blue: 255 / 255)
    static let novaMuted = Color(red: 180 / 255, green: 181 / 255, blue: 214 / 255)
    static let novaLine = Color(red: 133 / 255, green: 124 / 255, blue: 212 / 255, opacity: 0.45)
    static let novaLineStrong = Color(red: 201 / 255, green: 126 / 255, blue: 255 / 255, opacity: 0.66)
    static let novaBrand = Color(red: 41 / 255, green: 217 / 255, blue: 1)
    static let novaHot = Color(red: 1, green: 88 / 255, blue: 203 / 255)
    static let novaIndigo = Color(red: 111 / 255, green: 109 / 255, blue: 1)
    static let novaGood = Color(red: 59 / 255, green: 207 / 255, blue: 135 / 255)
    static let novaDanger = Color(red: 1, green: 95 / 255, blue: 142 / 255)
}
