#ifndef __MCRApp__
#define __MCRApp__
#include <core/GraphicalSimulationApp.h>
#include "MCRManager.h"
class MCRApp : public sf::GraphicalSimulationApp
{
public:
    MCRApp(std::string dataDirPath, sf::RenderSettings s, sf::HelperSettings h, MCRManager* sim);
    void DoHUD() override;
};
#endif
