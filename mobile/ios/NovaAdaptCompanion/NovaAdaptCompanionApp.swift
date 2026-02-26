import SwiftUI

@main
struct NovaAdaptCompanionApp: App {
    @StateObject private var bridge = BridgeViewModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(bridge)
                .onChange(of: scenePhase) { _, newPhase in
                    if newPhase == .background {
                        bridge.disconnect()
                    }
                }
        }
    }
}
