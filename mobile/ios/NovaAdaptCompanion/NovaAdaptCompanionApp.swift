import SwiftUI

@main
struct NovaAdaptCompanionApp: App {
    @StateObject private var bridge = BridgeViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(bridge)
        }
    }
}
