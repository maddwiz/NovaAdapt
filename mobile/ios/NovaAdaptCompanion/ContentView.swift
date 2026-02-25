import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var bridge: BridgeViewModel

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    statusCard
                    connectionCard
                    objectiveCard
                    plansCard
                    jobsCard
                    terminalCard
                    eventsCard
                    websocketCard
                }
                .padding()
            }
            .navigationTitle("NovaAdapt Companion")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Refresh") {
                        bridge.refreshDashboard()
                    }
                }
            }
            .onAppear {
                bridge.refreshDashboard()
            }
        }
    }

    private var statusCard: some View {
        sectionCard(title: "Status") {
            Text(bridge.status)
                .font(.subheadline)
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

            HStack {
                Button("Refresh Dashboard") { bridge.refreshDashboard() }
                    .buttonStyle(.borderedProminent)
                Spacer(minLength: 8)
                Button("Connect WS") { bridge.connect() }
                    .buttonStyle(.bordered)
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

            HStack {
                Button("Queue Async Run") { bridge.queueObjective() }
                    .buttonStyle(.borderedProminent)
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
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(bridge.plans.prefix(12))) { plan in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(plan.objective.isEmpty ? "(no objective)" : plan.objective)
                            .font(.headline)
                        Text("id: \(plan.id)")
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                        Text("status: \(plan.status) • strategy: \(plan.strategy) • actions: \(plan.actionCount) • progress: \(plan.progressCompleted)/\(plan.progressTotal)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        HStack {
                            if plan.status.lowercased() == "pending" {
                                Button("Approve + Execute") { bridge.approvePlan(plan.id) }
                                    .buttonStyle(.borderedProminent)
                                Button("Reject") { bridge.rejectPlan(plan.id) }
                                    .buttonStyle(.bordered)
                            }
                            if plan.status.lowercased() == "failed" {
                                Button("Retry Failed Steps") { bridge.retryFailedPlan(plan.id) }
                                    .buttonStyle(.borderedProminent)
                            }
                            if plan.hasUndoActions {
                                Button("Undo (Mark)") { bridge.markUndoPlan(plan.id) }
                                    .buttonStyle(.bordered)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
            }
        }
    }

    private var jobsCard: some View {
        sectionCard(title: "Jobs (\(bridge.activeJobs.count) active)") {
            if bridge.jobs.isEmpty {
                Text("No jobs loaded.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(bridge.jobs.prefix(12))) { job in
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(job.kind)
                                .font(.headline)
                            Text("id: \(job.id)")
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                            Text("status: \(job.status)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        if job.status.lowercased() == "running" || job.status.lowercased() == "queued" {
                            Button("Cancel") { bridge.cancelJob(job.id) }
                                .buttonStyle(.bordered)
                        }
                    }
                    .padding(10)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
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

            HStack {
                Button("Start Session") { bridge.startTerminalSession() }
                    .buttonStyle(.borderedProminent)
                Button("Attach Session") {
                    if !bridge.terminalSessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        bridge.attachTerminalSession(bridge.terminalSessionID)
                    }
                }
                .buttonStyle(.bordered)
                Button("Close") { bridge.closeTerminalSession() }
                    .buttonStyle(.bordered)
            }

            HStack {
                TextField("Type command", text: $bridge.terminalInput)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { bridge.sendTerminalLine() }
                    .buttonStyle(.borderedProminent)
                Button("Ctrl+C") { bridge.sendTerminalCtrlC() }
                    .buttonStyle(.bordered)
            }

            if bridge.terminalOutput.isEmpty {
                Text("No terminal output yet.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                Text(bridge.terminalOutput)
                    .font(.caption.monospaced())
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color.black.opacity(0.85))
                    .foregroundStyle(Color.green.opacity(0.95))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
    }

    private var eventsCard: some View {
        sectionCard(title: "Audit Events") {
            if bridge.events.isEmpty {
                Text("No events loaded.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(bridge.events.prefix(12))) { event in
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(event.category) / \(event.action)")
                            .font(.subheadline.weight(.semibold))
                        Text("status: \(event.status) • \(event.createdAt)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(10)
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
            }
        }
    }

    private var websocketCard: some View {
        sectionCard(title: "WebSocket Feed") {
            if bridge.wsEvents.isEmpty {
                Text("No websocket events yet.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(bridge.wsEvents.prefix(20)), id: \.self) { item in
                    Text(item)
                        .font(.caption.monospaced())
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                        .background(Color(.secondarySystemBackground))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
        }
    }

    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color(.separator), lineWidth: 1)
        )
    }
}
