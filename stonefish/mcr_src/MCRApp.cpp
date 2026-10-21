#include "MCRApp.h"
MCRApp::MCRApp(std::string dataDirPath, sf::RenderSettings s, sf::HelperSettings h, MCRManager* sim)
 : GraphicalSimulationApp("MaritimeCyberRange-AUV", dataDirPath, s, h, sim) {}
void MCRApp::DoHUD() { GraphicalSimulationApp::DoHUD(); }
