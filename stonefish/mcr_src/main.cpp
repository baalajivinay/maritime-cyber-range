#include "MCRApp.h"
#include "MCRManager.h"
#include <core/ConsoleSimulationApp.h>
#include <cstring>
#include <cstdlib>
#include <string>
int main(int argc, const char** argv)
{
    std::string scn = (argc > 1 && argv[1][0] != '-') ? std::string(argv[1])
                       : (std::string(DATA_DIR_PATH) + "underwater_test.scn");
    bool fdm = false; int port = 9002; bool headless = false;
    for(int i = 1; i < argc; ++i) {
        if(!strcmp(argv[i], "--fdm")) { fdm = true; if(i+1 < argc && argv[i+1][0] != '-') port = atoi(argv[++i]); }
        else if(!strcmp(argv[i], "--headless")) { headless = true; }
    }
    // Headless: physics + JSON FDM only, no window (Godot renders instead).
    if(headless)
    {
        MCRManager mgr(200.0, scn, fdm, port);
        mgr.setRealtimeFactor(1.0);
        sf::ConsoleSimulationApp app("MCR", std::string(DATA_DIR_PATH), &mgr);
        app.Run();
        return 0;
    }
    sf::RenderSettings s;
    s.windowW = 1200; s.windowH = 800;
    s.aa = sf::RenderQuality::HIGH; s.shadows = sf::RenderQuality::HIGH; s.ao = sf::RenderQuality::HIGH;
    s.atmosphere = sf::RenderQuality::MEDIUM; s.ocean = sf::RenderQuality::HIGH; s.ssr = sf::RenderQuality::HIGH;
    s.verticalSync = true;
    sf::HelperSettings h;
    h.showFluidDynamics = false; h.showCoordSys = false; h.showBulletDebugInfo = false;
    h.showSensors = false; h.showActuators = false; h.showForces = false;
    MCRManager mgr(200.0, scn, fdm, port);
    mgr.setRealtimeFactor(1.0);
    MCRApp app(std::string(DATA_DIR_PATH), s, h, &mgr);
    app.Run();
    return 0;
}
