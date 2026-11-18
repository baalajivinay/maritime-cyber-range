#ifndef __MCRManager__
#define __MCRManager__

#include <core/SimulationManager.h>
#include <string>
#include <netinet/in.h>

// Maritime Cyber Range: loads a .scn AUV and (optionally) bridges it to
// ArduPilot/ArduSub SITL via the JSON SIM_JSON FDM protocol.
class MCRManager : public sf::SimulationManager
{
public:
    MCRManager(sf::Scalar sps, const std::string& scnPath, bool fdm, int fdmPort);
    ~MCRManager();
    void BuildScenario() override;
    void SimulationStepCompleted(sf::Scalar timeStep) override;

private:
    std::string scnPath_;
    bool fdm_;
    int fdmPort_;
    int sock_;
    bool haveClient_;
    struct sockaddr_in clientAddr_;
    double simTime_;
    void fdmInit();
    void fdmStep(sf::Scalar dt);
};

#endif
