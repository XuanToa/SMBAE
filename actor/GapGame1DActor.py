import sys
import math
from actor.ActorInterface import ActorInterface

class GapGame1DActor(ActorInterface):
    
    def __init__(self, discrete_actions, experience):
        super(GapGame1DActor,self).__init__(discrete_actions, experience)
        self._target_vel_weight=self._settings["target_velocity_decay"]
        self._target_vel = self._settings["target_velocity"]
        
    
    # @profile(precision=5)
    def act(self, exp, action_, bootstrapping=False):
        samp = self.getActionParams(action_)
        
        reward = self.actContinuous(exp, samp, bootstrapping=bootstrapping)
        
        return reward
    
    # @profile(precision=5)
    def actContinuous(self, exp, action_, bootstrapping=False):
        # Actor should be FIRST here
        # print "Action: " + str(action_)
        averageSpeed = exp.getEnvironment().actContinuous(action_, bootstrapping=bootstrapping)
        
        if (self.hasNotFallen(exp)):
            vel_dif = self._target_vel - averageSpeed
            reward = math.exp((vel_dif*vel_dif)*self._target_vel_weight) # optimal is 0
        else:
            return 0.0
        
        self._reward_sum = self._reward_sum + reward
        return reward
    
    def getEvaluationData(self):
        return self._reward_sum
    
    def hasNotFallen(self, exp):
        # if ( (not ( exp.getEnvironment().agentHasFallen() or exp.getEnvironment().hitWall())) and () ):
        # if ( exp.getEnvironment().agentHasFallen() or exp.getEnvironment().hitWall()) :
        if ( exp.getEnvironment().agentHasFallen() ):
            return 0
        else:
            return 1