import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var bridge: BridgeViewModel

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                TextField("Bridge WS URL", text: $bridge.bridgeURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
                    .textFieldStyle(.roundedBorder)

                SecureField("Bridge Token", text: $bridge.token)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button("Connect") { bridge.connect() }
                    Button("Disconnect") { bridge.disconnect() }
                }

                TextField("Objective", text: $bridge.objective)
                    .textFieldStyle(.roundedBorder)
                Button("Run Objective") { bridge.submitObjective() }

                List(bridge.events, id: \.self) { item in
                    Text(item)
                        .font(.system(.caption, design: .monospaced))
                }
            }
            .padding()
            .navigationTitle("NovaAdapt Companion")
        }
    }
}
