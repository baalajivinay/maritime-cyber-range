#include "MCRManager.h"
#include <core/ScenarioParser.h>
#include <core/Robot.h>
#include <core/NED.h>
#include <entities/SolidEntity.h>
#include <actuators/Thruster.h>
#include <utils/SystemUtil.hpp>
#include <cstring>
#include <cstdio>
#include <unistd.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <array>

// ArduPilot SIM_JSON servo packet (SITL -> FDM)
#pragma pack(push, 1)
struct ServoPacket {
    uint16_t magic;        // 18458
    uint16_t frame_rate;
    uint32_t frame_count;
    uint16_t pwm[16];
};
#pragma pack(pop)

static const char* THR_NAMES[5] = {"ThrSurge", "ThrHeaveBow", "ThrHeaveStern", "ThrSwayBow", "ThrSwayStern"};

MCRManager::MCRManager(sf::Scalar sps, const std::string& scnPath, bool fdm, int fdmPort)
 : SimulationManager(sps, sf::Solver::SI, sf::CollisionFilter::EXCLUSIVE),
   scnPath_(scnPath), fdm_(fdm), fdmPort_(fdmPort), sock_(-1), haveClient_(false), simTime_(0.0)
{
}

MCRManager::~MCRManager()
{
    if(sock_ >= 0) close(sock_);
}

void MCRManager::BuildScenario()
{
    sf::ScenarioParser parser(this);
    bool ok = parser.Parse(scnPath_);
    parser.SaveLog("/tmp/mcr_parse.log");
    if(!ok) {
        cCritical("MCR: failed to parse scenario '%s'", scnPath_.c_str());
    } else {
        cInfo("MCR: scenario '%s' loaded.", scnPath_.c_str());
    }
    setCallSimulationStepCompleted(true);   // enable the per-step FDM callback
    if(fdm_)
        fdmInit();
}

void MCRManager::fdmInit()
{
    sock_ = socket(AF_INET, SOCK_DGRAM, 0);
    int flags = fcntl(sock_, F_GETFL, 0);
    fcntl(sock_, F_SETFL, flags | O_NONBLOCK);
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(fdmPort_);
    if(bind(sock_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        cCritical("MCR-FDM: cannot bind UDP :%d", fdmPort_);
    } else {
        cInfo("MCR-FDM: ArduSub JSON FDM listening on :%d", fdmPort_);
    }
}

void MCRManager::SimulationStepCompleted(sf::Scalar timeStep)
{
    simTime_ += timeStep;
    if(fdm_ && sock_ >= 0)
        fdmStep(timeStep);
}

void MCRManager::fdmStep(sf::Scalar dt)
{
    // 1) receive latest servo PWM from ArduSub (non-blocking; drain)
    ServoPacket sp;
    struct sockaddr_in src;
    socklen_t slen = sizeof(src);
    bool got = false;
    while(true)
    {
        ssize_t n = recvfrom(sock_, &sp, sizeof(sp), 0, (struct sockaddr*)&src, &slen);
        if(n == (ssize_t)sizeof(sp) && sp.magic == 18458)
        {
            clientAddr_ = src; haveClient_ = true; got = true;
        }
        else break;
    }
    if(got)
    {
        static bool first = true;
        if(first) { cInfo("MCR-FDM: ArduSub connected -- receiving servo PWM, driving thrusters."); first = false; }
        for(int i = 0; i < 5; ++i)
        {
            sf::Thruster* t = dynamic_cast<sf::Thruster*>(getActuator(THR_NAMES[i]));
            if(t)
            {
                sf::Scalar s = (sf::Scalar(sp.pwm[i]) - 1500.0) / 400.0;  // -1..1
                if(s > 1.0) s = 1.0; if(s < -1.0) s = -1.0;
                t->setSetpoint(s);
            }
        }
    }
    // 2) send sensor JSON to ArduSub
    if(!haveClient_) return;
    sf::Robot* robot = getRobot((unsigned int)0);
    if(!robot) return;
    sf::SolidEntity* base = robot->getBaseLink();
    if(!base) return;
    sf::Transform T = base->getOTransform();
    sf::Vector3 pos = T.getOrigin();                 // NED (x=N, y=E, z=D)
    sf::Matrix3 R(T.getRotation());
    sf::Scalar roll, pitch, yaw;
    R.getEulerYPR(yaw, pitch, roll);
    sf::Vector3 vW = base->getLinearVelocity();      // world NED
    sf::Vector3 gyro = R.transpose() * base->getAngularVelocity();
    sf::Vector3 acc = R.transpose() * (base->getLinearAcceleration() - sf::Vector3(0, 0, 9.81));

    char buf[1024];
    int len = snprintf(buf, sizeof(buf),
        "{\"timestamp\":%.6f,"
        "\"imu\":{\"gyro\":[%.5f,%.5f,%.5f],\"accel_body\":[%.5f,%.5f,%.5f]},"
        "\"position\":[%.4f,%.4f,%.4f],"
        "\"attitude\":[%.5f,%.5f,%.5f],"
        "\"velocity\":[%.4f,%.4f,%.4f]}\n",
        simTime_,
        gyro.x(), gyro.y(), gyro.z(), acc.x(), acc.y(), acc.z(),
        pos.x(), pos.y(), pos.z(),
        roll, pitch, yaw,
        vW.x(), vW.y(), vW.z());
    sendto(sock_, buf, len, 0, (struct sockaddr*)&clientAddr_, sizeof(clientAddr_));

    // Broadcast the AUV's TRUE pose (N,E,D,yaw) on :9005 (~20 Hz) for the
    // ExternalNav/acoustic feed -- this is the USBL ground truth the attack
    // layer forges to spoof the submerged vehicle's position.
    static int pctr = 0;
    if((++pctr % 10) == 0)
    {
        char pbuf[256];
        int plen = snprintf(pbuf, sizeof(pbuf),
            "{\"n\":%.4f,\"e\":%.4f,\"d\":%.4f,\"yaw\":%.5f}\n",
            pos.x(), pos.y(), pos.z(), yaw);
        struct sockaddr_in pa;
        memset(&pa, 0, sizeof(pa));
        pa.sin_family = AF_INET; pa.sin_port = htons(9005);
        inet_pton(AF_INET, "127.0.0.1", &pa.sin_addr);
        sendto(sock_, pbuf, plen, 0, (struct sockaddr*)&pa, sizeof(pa));
    }
}
