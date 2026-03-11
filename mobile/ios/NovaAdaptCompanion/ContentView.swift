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
                        controlArtifactsCard
                        runtimeGovernanceCard
                        agentMarketplaceCard
                        iotControlCard
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
                bridge.refreshMQTTStatus()
                bridge.refreshTemplates()
                bridge.ensureLiveEventStream()
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

            itemCard {
                VStack(alignment: .leading, spacing: 8) {
                    Toggle("Live Audit Stream", isOn: Binding(
                        get: { bridge.liveEventsEnabled },
                        set: { bridge.liveEventsEnabled = $0 }
                    ))
                    .foregroundStyle(Color.novaInk)
                    .tint(.novaHot)

                    HStack {
                        Text(bridge.liveEventsConnected ? "Connected" : "Standby")
                            .font(.headline)
                            .foregroundStyle(bridge.liveEventsConnected ? Color.novaGood : Color.novaMuted)
                        Spacer()
                        Text("\(bridge.liveAuditEventsSeen) events")
                            .font(.caption.monospaced())
                            .foregroundStyle(Color.novaMuted)
                    }

                    Text(bridge.liveEventsStatus)
                        .font(.caption)
                        .foregroundStyle(Color.novaMuted)
                }
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
                Text("decompose").tag("decompose")
            }
            .pickerStyle(.segmented)

            TextField("Candidate models (CSV)", text: $bridge.candidatesCSV)
                .textFieldStyle(.roundedBorder)

            Toggle("Execute actions immediately", isOn: $bridge.execute)
                .foregroundStyle(Color.novaInk)
                .tint(.novaHot)

            Stepper("Auto-repair attempts: \(bridge.autoRepairAttempts)", value: $bridge.autoRepairAttempts, in: 0 ... 10)
                .foregroundStyle(Color.novaInk)

            Picker("Repair Strategy", selection: $bridge.repairStrategy) {
                Text("decompose").tag("decompose")
                Text("single").tag("single")
                Text("vote").tag("vote")
            }
            .pickerStyle(.segmented)

            TextField("Repair model (optional)", text: $bridge.repairModel)
                .textFieldStyle(.roundedBorder)

            TextField("Repair candidates (CSV)", text: $bridge.repairCandidatesCSV)
                .textFieldStyle(.roundedBorder)

            TextField("Repair fallbacks (CSV)", text: $bridge.repairFallbacksCSV)
                .textFieldStyle(.roundedBorder)

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
                            if !plan.executionError.isEmpty {
                                Text("error: \(plan.executionError)")
                                    .font(.caption)
                                    .foregroundStyle(Color.novaDanger)
                            }
                            if !plan.repairSummary.isEmpty {
                                Text("repair: \(plan.repairSummary)")
                                    .font(.caption)
                                    .foregroundStyle(Color.novaGood)
                            }
                            if !plan.collaborationSummary.isEmpty {
                                Text("collab: \(plan.collaborationSummary)")
                                    .font(.caption)
                                    .foregroundStyle(Color.novaBrand)
                            }
                            if !plan.transcriptPreview.isEmpty {
                                VStack(alignment: .leading, spacing: 2) {
                                    ForEach(Array(plan.transcriptPreview.enumerated()), id: \.offset) { _, line in
                                        Text("• \(line)")
                                            .font(.caption2)
                                            .foregroundStyle(Color.novaMuted)
                                    }
                                }
                            }
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
                                if !job.objective.isEmpty {
                                    Text(job.objective)
                                        .font(.caption)
                                        .foregroundStyle(Color.novaInk)
                                }
                                if !job.resultSummary.isEmpty {
                                    Text(job.resultSummary)
                                        .font(.caption)
                                        .foregroundStyle(Color.novaMuted)
                                }
                                if !job.error.isEmpty {
                                    Text("error: \(job.error)")
                                        .font(.caption)
                                        .foregroundStyle(Color.novaDanger)
                                }
                                if !job.repairSummary.isEmpty {
                                    Text("repair: \(job.repairSummary)")
                                        .font(.caption)
                                        .foregroundStyle(Color.novaGood)
                                }
                                if !job.collaborationSummary.isEmpty {
                                    Text("collab: \(job.collaborationSummary)")
                                        .font(.caption)
                                        .foregroundStyle(Color.novaBrand)
                                }
                                if !job.transcriptPreview.isEmpty {
                                    VStack(alignment: .leading, spacing: 2) {
                                        ForEach(Array(job.transcriptPreview.enumerated()), id: \.offset) { _, line in
                                            Text("• \(line)")
                                                .font(.caption2)
                                                .foregroundStyle(Color.novaMuted)
                                        }
                                    }
                                }
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

    private var controlArtifactsCard: some View {
        sectionCard(title: "Control Artifacts") {
            if bridge.controlArtifacts.isEmpty {
                Text("No control artifacts yet.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                ForEach(Array(bridge.controlArtifacts.prefix(8))) { artifact in
                    itemCard {
                        VStack(alignment: .leading, spacing: 8) {
                            if let url = bridge.controlArtifactPreviewURL(for: artifact) {
                                AsyncImage(url: url) { phase in
                                    switch phase {
                                    case .empty:
                                        ProgressView()
                                            .frame(maxWidth: .infinity)
                                            .padding(.vertical, 12)
                                    case .success(let image):
                                        image
                                            .resizable()
                                            .scaledToFit()
                                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                                    case .failure:
                                        Text("Preview unavailable")
                                            .font(.caption)
                                            .foregroundStyle(Color.novaMuted)
                                    @unknown default:
                                        EmptyView()
                                    }
                                }
                            }
                            Text([artifact.controlType, artifact.platform.isEmpty ? artifact.transport : artifact.platform]
                                .filter { !$0.isEmpty }
                                .joined(separator: " / "))
                                .font(.headline)
                                .foregroundStyle(.white)
                            Text("status: \(artifact.status) • \(artifact.createdAt)")
                                .font(.caption)
                                .foregroundStyle(Color.novaMuted)
                            Text(artifact.goal.isEmpty ? artifact.outputPreview : artifact.goal)
                                .font(.subheadline)
                                .foregroundStyle(Color.novaInk)
                            Text("action: \(artifact.actionType)\(artifact.target.isEmpty ? "" : " • \(artifact.target)")")
                                .font(.caption)
                                .foregroundStyle(Color.novaMuted)
                            Text("model: \(artifact.model.isEmpty ? "n/a" : artifact.model)\(artifact.dangerous ? " • dangerous" : "")")
                                .font(.caption)
                                .foregroundStyle(artifact.dangerous ? Color.novaDanger : Color.novaMuted)
                        }
                    }
                }
            }
        }
    }

    private var runtimeGovernanceCard: some View {
        sectionCard(title: "Runtime Governance") {
            itemCard {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(bridge.governancePaused ? "Paused" : "Active")
                            .font(.headline)
                            .foregroundStyle(bridge.governancePaused ? Color.novaDanger : Color.novaGood)
                        Spacer()
                        Text("active runs \(bridge.governanceActiveRuns)")
                            .font(.caption.monospaced())
                            .foregroundStyle(Color.novaMuted)
                    }

                    if !bridge.governancePauseReason.isEmpty {
                        Text(bridge.governancePauseReason)
                            .font(.caption)
                            .foregroundStyle(Color.novaMuted)
                    }

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        governanceMetric(title: "Spend", value: currencyString(bridge.governanceSpendEstimateUSD))
                        governanceMetric(title: "LLM Calls", value: "\(bridge.governanceLLMCallsTotal)")
                        governanceMetric(title: "Runs", value: "\(bridge.governanceRunsTotal)")
                        governanceMetric(title: "Jobs", value: "\(bridge.governanceJobActive) active")
                    }

                    HStack(spacing: 8) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Budget Limit (USD)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Color.novaMuted)
                            TextField("optional", text: $bridge.governanceBudgetLimit)
                                .keyboardType(.decimalPad)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled(true)
                                .textFieldStyle(.roundedBorder)
                        }
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Max Active Runs")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Color.novaMuted)
                            TextField("optional", text: $bridge.governanceMaxActiveRuns)
                                .keyboardType(.numberPad)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled(true)
                                .textFieldStyle(.roundedBorder)
                        }
                    }

                    HStack {
                        Button("Refresh") { bridge.refreshRuntimeGovernance() }
                            .buttonStyle(.bordered)
                        Button("Apply") { bridge.applyRuntimeGovernance() }
                            .buttonStyle(.borderedProminent)
                            .tint(.novaBrand)
                    }

                    HStack {
                        Button("Pause") { pendingConfirmation = .pauseRuntime }
                            .buttonStyle(.bordered)
                            .tint(.novaDanger)
                        Button("Resume") { pendingConfirmation = .resumeRuntime }
                            .buttonStyle(.bordered)
                            .tint(.novaGood)
                        Button("Reset Usage") { pendingConfirmation = .resetRuntimeUsage }
                            .buttonStyle(.bordered)
                    }

                    HStack {
                        Text("queued \(bridge.governanceJobQueued) • running \(bridge.governanceJobRunning)")
                            .font(.caption.monospaced())
                            .foregroundStyle(Color.novaMuted)
                        Spacer()
                        if bridge.governanceJobMaxWorkers > 0 {
                            Text("workers \(bridge.governanceJobMaxWorkers)")
                                .font(.caption.monospaced())
                                .foregroundStyle(Color.novaMuted)
                        }
                    }

                    Button("Cancel All Jobs") { pendingConfirmation = .cancelAllJobs }
                        .buttonStyle(.borderedProminent)
                        .tint(.novaDanger)

                    if !bridge.governanceLastObjectivePreview.isEmpty {
                        Text("Last objective: \(bridge.governanceLastObjectivePreview)")
                            .font(.caption)
                            .foregroundStyle(Color.novaMuted)
                    }

                    Text("Strategy: \(bridge.governanceLastStrategy.isEmpty ? "single" : bridge.governanceLastStrategy) • Last run: \(bridge.governanceLastRunAt.isEmpty ? "-" : bridge.governanceLastRunAt)")
                        .font(.caption)
                        .foregroundStyle(Color.novaMuted)

                    Text("Updated: \(bridge.governanceUpdatedAt.isEmpty ? "-" : bridge.governanceUpdatedAt)")
                        .font(.caption)
                        .foregroundStyle(Color.novaMuted)

                    if !bridge.governancePerModel.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Model Usage")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Color.novaMuted)
                            ForEach(Array(bridge.governancePerModel.prefix(6))) { item in
                                HStack(alignment: .top) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.label)
                                            .font(.subheadline.weight(.semibold))
                                            .foregroundStyle(.white)
                                        if !item.modelID.isEmpty {
                                            Text(item.modelID)
                                                .font(.caption.monospaced())
                                                .foregroundStyle(Color.novaMuted)
                                        }
                                    }
                                    Spacer()
                                    Text("\(item.calls) calls • \(currencyString(item.estimatedCostUSD))")
                                        .font(.caption.monospaced())
                                        .foregroundStyle(Color.novaMuted)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private var iotControlCard: some View {
        sectionCard(title: "IoT Control") {
            TextField("Entity domain (light, switch, vacuum)", text: $bridge.iotDomainFilter)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            TextField("Entity prefix (light.office)", text: $bridge.iotEntityPrefix)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Refresh Entities") { bridge.refreshIoTEntities() }
                    .buttonStyle(.borderedProminent)
                    .tint(.novaBrand)
                Button("MQTT Status") { bridge.refreshMQTTStatus() }
                    .buttonStyle(.bordered)
            }

            Text(bridge.mqttStatusSummary)
                .font(.caption)
                .foregroundStyle(Color.novaMuted)

            if bridge.homeAssistantEntities.isEmpty {
                Text("No Home Assistant entities loaded.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                ForEach(Array(bridge.homeAssistantEntities.prefix(10))) { entity in
                    itemCard {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(entity.friendlyName)
                                    .font(.headline)
                                    .foregroundStyle(.white)
                                Spacer()
                                Text(entity.state)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(Color.novaBrand)
                            }
                            Text(entity.entityID)
                                .font(.caption.monospaced())
                                .foregroundStyle(Color.novaMuted)
                            Text(entity.detail)
                                .font(.caption)
                                .foregroundStyle(Color.novaMuted)
                            HStack {
                                ForEach(quickActions(for: entity)) { action in
                                    Button(action.label) {
                                        pendingConfirmation = .executeIoT(entity.entityID, entity.domain, action.service)
                                    }
                                    .buttonStyle(.bordered)
                                    .tint(action.service == "turn_off" || action.service == "close_cover" ? .novaDanger : .novaBrand)
                                }
                            }
                        }
                    }
                }
            }

            TextField("MQTT topic", text: $bridge.mqttTopic)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            VStack(alignment: .leading, spacing: 6) {
                Text("MQTT Payload")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.novaMuted)
                TextEditor(text: $bridge.mqttPayload)
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 78)
                    .padding(8)
                    .background(Color.black.opacity(0.18))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke(Color.novaLine.opacity(0.85), lineWidth: 1)
                    )
                    .foregroundStyle(Color.novaInk)
            }

            Toggle("Retain MQTT publish", isOn: $bridge.mqttRetain)
                .foregroundStyle(Color.novaInk)
                .tint(.novaHot)

            HStack {
                Button("Publish MQTT") { pendingConfirmation = .publishMQTT }
                    .buttonStyle(.borderedProminent)
                    .tint(.novaHot)
                Button("Subscribe Snapshot") { bridge.subscribeMQTTSnapshot() }
                    .buttonStyle(.bordered)
            }

            if bridge.mqttMessages.isEmpty {
                Text("No MQTT messages captured yet.")
                    .font(.subheadline)
                    .foregroundStyle(Color.novaMuted)
            } else {
                ForEach(Array(bridge.mqttMessages.prefix(8))) { message in
                    itemCard {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(message.topic)
                                .font(.headline)
                                .foregroundStyle(.white)
                            Text("qos \(message.qos)\(message.retain ? " • retain" : "") • \(message.receivedAt)")
                                .font(.caption)
                                .foregroundStyle(Color.novaMuted)
                            Text(message.payload.isEmpty ? "(empty payload)" : message.payload)
                                .font(.caption.monospaced())
                                .foregroundStyle(Color.novaInk)
                        }
                    }
                }
            }
        }
    }

    private var agentMarketplaceCard: some View {
        sectionCard(title: "Agent Marketplace") {
            TextField("Tag filter", text: $bridge.templateTagFilter)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Refresh") { bridge.refreshTemplates() }
                    .buttonStyle(.bordered)
                Button("Export Current") { bridge.exportCurrentTemplate() }
                    .buttonStyle(.borderedProminent)
                    .tint(.novaBrand)
                Button("Import Manifest") { bridge.importTemplateManifest() }
                    .buttonStyle(.bordered)
            }

            Text(bridge.templateStatus)
                .font(.caption)
                .foregroundStyle(Color.novaMuted)

            VStack(alignment: .leading, spacing: 6) {
                Text("Manifest JSON")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.novaMuted)
                TextEditor(text: $bridge.templateManifestJSON)
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 96)
                    .padding(8)
                    .background(Color.black.opacity(0.18))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke(Color.novaLine.opacity(0.85), lineWidth: 1)
                    )
                    .foregroundStyle(Color.novaInk)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Local Templates")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.novaMuted)
                if bridge.templateLibrary.isEmpty {
                    Text("No local templates yet.")
                        .font(.subheadline)
                        .foregroundStyle(Color.novaMuted)
                } else {
                    ForEach(bridge.templateLibrary) { template in
                        itemCard {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(template.name)
                                        .font(.headline)
                                        .foregroundStyle(.white)
                                    Spacer()
                                    Text(template.updatedAt)
                                        .font(.caption.monospaced())
                                        .foregroundStyle(Color.novaMuted)
                                }
                                Text(template.description.isEmpty ? template.objective : template.description)
                                    .font(.caption)
                                    .foregroundStyle(Color.novaMuted)
                                Text(template.objective)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(Color.novaInk)
                                Text(templateSummary(template))
                                    .font(.caption)
                                    .foregroundStyle(Color.novaMuted)
                                HStack {
                                    Button("Use") { bridge.useTemplateObjective(template) }
                                        .buttonStyle(.bordered)
                                    Button("Plan") { bridge.createPlanFromTemplate(template) }
                                        .buttonStyle(.borderedProminent)
                                        .tint(.novaBrand)
                                    Button("Share") { bridge.shareTemplate(template) }
                                        .buttonStyle(.bordered)
                                }
                                if template.shared, !template.shareURL.isEmpty {
                                    Text(template.shareURL)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(Color.novaBrand)
                                }
                            }
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Gallery")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color.novaMuted)
                if bridge.templateGallery.isEmpty {
                    Text("No gallery templates matched the current filter.")
                        .font(.subheadline)
                        .foregroundStyle(Color.novaMuted)
                } else {
                    ForEach(bridge.templateGallery) { template in
                        itemCard {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(template.name)
                                        .font(.headline)
                                        .foregroundStyle(.white)
                                    Spacer()
                                    Text(template.source)
                                        .font(.caption.monospaced())
                                        .foregroundStyle(Color.novaBrand)
                                }
                                Text(template.description.isEmpty ? template.objective : template.description)
                                    .font(.caption)
                                    .foregroundStyle(Color.novaMuted)
                                Text(templateSummary(template))
                                    .font(.caption)
                                    .foregroundStyle(Color.novaMuted)
                                HStack {
                                    Button("Use") { bridge.useTemplateObjective(template) }
                                        .buttonStyle(.bordered)
                                    Button("Import") { bridge.importGalleryTemplate(template) }
                                        .buttonStyle(.borderedProminent)
                                        .tint(.novaHot)
                                }
                            }
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

    private func governanceMetric(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(Color.novaMuted)
            Text(value)
                .font(.headline)
                .foregroundStyle(.white)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.black.opacity(0.14))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Color.novaLine.opacity(0.8), lineWidth: 1)
        )
    }

    private func currencyString(_ value: Double) -> String {
        String(format: "$%.4f", value)
    }

    private func templateSummary(_ template: AgentTemplateSummary) -> String {
        let tags = template.tags.joined(separator: ", ")
        var parts = ["strategy \(template.strategy)", "source \(template.source)"]
        if !tags.isEmpty {
            parts.append("tags \(tags)")
        }
        return parts.joined(separator: " • ")
    }
}

private enum PendingConfirmation {
    case revokeSession
    case removeAllowlistedDevice
    case approvePlan(String)
    case rejectPlan(String)
    case retryFailed(String)
    case cancelJob(String)
    case pauseRuntime
    case resumeRuntime
    case resetRuntimeUsage
    case cancelAllJobs
    case executeIoT(String, String, String)
    case publishMQTT
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
        case .pauseRuntime:
            return "Pause the runtime?"
        case .resumeRuntime:
            return "Resume the runtime?"
        case .resetRuntimeUsage:
            return "Reset runtime usage counters?"
        case .cancelAllJobs:
            return "Cancel all jobs and pause runtime?"
        case .executeIoT:
            return "Execute IoT action?"
        case .publishMQTT:
            return "Publish MQTT message?"
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
        case .pauseRuntime:
            return "New runs will be blocked until the runtime is resumed."
        case .resumeRuntime:
            return "Queued controls and new runs can proceed again."
        case .resetRuntimeUsage:
            return "Spend estimates and per-model counters will be cleared."
        case .cancelAllJobs:
            return "All queued and running jobs will be canceled or marked for cancellation, and runtime will be paused."
        case let .executeIoT(entityID, domain, service):
            return "\(domain).\(service) will run for \(entityID)."
        case .publishMQTT:
            return "The current MQTT topic and payload will be published immediately."
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
        case .pauseRuntime:
            bridge.pauseRuntime()
        case .resumeRuntime:
            bridge.resumeRuntime()
        case .resetRuntimeUsage:
            bridge.resetRuntimeUsage()
        case .cancelAllJobs:
            bridge.cancelAllJobs()
        case let .executeIoT(entityID, domain, service):
            bridge.executeHomeAssistantService(entityID: entityID, domain: domain, service: service)
        case .publishMQTT:
            bridge.publishMQTTMessage()
        }
    }

    func quickActions(for entity: HomeAssistantEntitySummary) -> [EntityQuickAction] {
        switch entity.domain {
        case "light", "switch", "input_boolean":
            return [
                EntityQuickAction(label: "On", service: "turn_on"),
                EntityQuickAction(label: "Off", service: "turn_off"),
                EntityQuickAction(label: "Toggle", service: "toggle"),
            ]
        case "cover":
            return [
                EntityQuickAction(label: "Open", service: "open_cover"),
                EntityQuickAction(label: "Close", service: "close_cover"),
                EntityQuickAction(label: "Stop", service: "stop_cover"),
            ]
        case "vacuum":
            return [
                EntityQuickAction(label: "Start", service: "start"),
                EntityQuickAction(label: "Pause", service: "pause"),
                EntityQuickAction(label: "Dock", service: "return_to_base"),
            ]
        case "scene", "script":
            return [EntityQuickAction(label: "Run", service: "turn_on")]
        default:
            return [EntityQuickAction(label: "Execute", service: "turn_on")]
        }
    }
}

private struct EntityQuickAction: Identifiable {
    let label: String
    let service: String

    var id: String { service }
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
