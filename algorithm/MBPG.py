## Nothing for now...

# from modular_rl import *

# ================================================================
# Model Based Policy Optimization
# ================================================================


import theano
from theano import tensor as T
from lasagne.layers import get_all_params
import numpy as np
import lasagne
import sys
import copy
sys.path.append('../')
from algorithm.AlgorithmInterface import AlgorithmInterface
from model.ModelUtil import norm_state, scale_state, norm_action, scale_action, action_bound_std, scale_reward
from model.LearningUtil import loglikelihood, likelihood, likelihoodMEAN, kl, entropy, flatgrad, zipsame, get_params_flat, setFromFlat 

class MBPG(AlgorithmInterface):
    
    def __init__(self, model, n_in, n_out, state_bounds, action_bounds, reward_bound, settings_):

        super(MBPG,self).__init__(model, n_in, n_out, state_bounds, action_bounds, reward_bound, settings_)
        # scale = (bounds[1][i]-bounds[0][i])/2.0
        # create a small convolutional neural network
        
        # self._action_std_scaling = (self._action_bounds[1] - self._action_bounds[0]) / 2.0
        
        self._NotFallen = T.bcol("Not_Fallen")
        ## because float64 <= float32 * int32, need to use int16 or int8
        self._NotFallen.tag.test_value = np.zeros((self._batch_size,1),dtype=np.dtype('int8'))
        
        self._NotFallen_shared = theano.shared(
            np.zeros((self._batch_size, 1), dtype='int8'),
            broadcastable=(False, True))
        
        self._advantage = T.col("Advantage")
        self._advantage.tag.test_value = np.zeros((self._batch_size,1),dtype=np.dtype(self.getSettings()['float_type']))
        
        self._advantage_shared = theano.shared(
            np.zeros((self._batch_size, 1), dtype=self.getSettings()['float_type']),
            broadcastable=(False, True))
        
        self._dyna_target = T.col("DYNA_Target")
        self._dyna_target.tag.test_value = np.zeros((self._batch_size,1),dtype=np.dtype(self.getSettings()['float_type']))
        
        self._dyna_target_shared = theano.shared(
            np.zeros((self._batch_size, 1), dtype=self.getSettings()['float_type']),
            broadcastable=(False, True))
        
        self._KL_Weight = T.scalar("KL_Weight")
        self._KL_Weight.tag.test_value = np.zeros((1),dtype=np.dtype(self.getSettings()['float_type']))[0]
        
        self._kl_weight_shared = theano.shared(
            np.ones((1), dtype=self.getSettings()['float_type'])[0])
        self._kl_weight_shared.set_value(self.getSettings()['previous_value_regularization_weight'])
        
        """
        self._target_shared = theano.shared(
            np.zeros((self._batch_size, 1), dtype='float64'),
            broadcastable=(False, True))
        """
        self._critic_regularization_weight = self.getSettings()["critic_regularization_weight"]
        self._critic_learning_rate = self.getSettings()["critic_learning_rate"]
        # primary network
        self._model = model
        # Target network
        self._modelTarget = copy.deepcopy(model)
        
        self._q_valsA = lasagne.layers.get_output(self._model.getCriticNetwork(), self._model.getStateSymbolicVariable(), deterministic=True)
        self._q_valsA_drop = lasagne.layers.get_output(self._model.getCriticNetwork(), self._model.getStateSymbolicVariable(), deterministic=False)
        self._q_valsNextState = lasagne.layers.get_output(self._model.getCriticNetwork(), self._model.getResultStateSymbolicVariable(), deterministic=True)
        self._q_valsTargetNextState = lasagne.layers.get_output(self._modelTarget.getCriticNetwork(), self._model.getResultStateSymbolicVariable(), deterministic=True)
        self._q_valsTarget = lasagne.layers.get_output(self._modelTarget.getCriticNetwork(), self._model.getStateSymbolicVariable(), deterministic=True)
        self._q_valsTarget_drop = lasagne.layers.get_output(self._modelTarget.getCriticNetwork(), self._model.getStateSymbolicVariable(), deterministic=False)
        
        self._q_valsActA = lasagne.layers.get_output(self._model.getActorNetwork(), self._model.getStateSymbolicVariable(), deterministic=True)[:,:self._action_length]
        # self._q_valsActA = scale_action(self._q_valsActA, self._action_bounds)
        self._q_valsActASTD = lasagne.layers.get_output(self._model.getActorNetwork(), self._model.getStateSymbolicVariable(), deterministic=True)[:,self._action_length:]
        
        ## prevent value from being 0
        """
        if ( 'use_fixed_std' in self.getSettings() and ( self.getSettings()['use_fixed_std'])): 
            self._q_valsActASTD = ( T.ones_like(self._q_valsActA)) * self.getSettings()['exploration_rate']
            # self._q_valsActASTD = ( T.ones_like(self._q_valsActA)) * self.getSettings()['exploration_rate']
        else:
        """
        self._q_valsActASTD = ((self._q_valsActASTD) * self.getSettings()['exploration_rate']) + 2e-2
       
        self._q_valsActTarget = lasagne.layers.get_output(self._modelTarget.getActorNetwork(), self._model.getStateSymbolicVariable())[:,:self._action_length]
        # self._q_valsActTarget = scale_action(self._q_valsActTarget, self._action_bounds)
        self._q_valsActTargetSTD = lasagne.layers.get_output(self._modelTarget.getActorNetwork(), self._model.getStateSymbolicVariable())[:,self._action_length:]
        """
        if ( 'use_fixed_std' in self.getSettings() and ( self.getSettings()['use_fixed_std'])): 
            self._q_valsActTargetSTD = (T.ones_like(self._q_valsActTarget)) * self.getSettings()['exploration_rate']
            # self._q_valsActTargetSTD = (self._action_std_scaling * T.ones_like(self._q_valsActTarget)) * self.getSettings()['exploration_rate']
        else:
        """ 
        self._q_valsActTargetSTD = (( self._q_valsActTargetSTD)  * self.getSettings()['exploration_rate']) + 2e-2
        self._q_valsActA_drop = lasagne.layers.get_output(self._model.getActorNetwork(), self._model.getStateSymbolicVariable(), deterministic=False)
        
        self._q_func = self._q_valsA
        self._q_funcTarget = self._q_valsTarget
        self._q_func_drop = self._q_valsA_drop
        self._q_funcTarget_drop = self._q_valsTarget_drop
        self._q_funcAct = self._q_valsActA
        self._q_funcAct_drop = self._q_valsActA_drop
        
        # self._target = (self._model.getRewardSymbolicVariable() + (np.array([self._discount_factor] ,dtype=np.dtype(self.getSettings()['float_type']))[0] * self._q_valsTargetNextState )) * self._NotFallen
        # self._target = T.mul(T.add(self._model.getRewardSymbolicVariable(), T.mul(self._discount_factor, self._q_valsTargetNextState )), self._NotFallen) + (self._NotFallen - 1)
        self._target = self._model.getRewardSymbolicVariable() +  (self._discount_factor * self._q_valsTargetNextState )
        self._diff = self._target - self._q_func
        self._diff_drop = self._target - self._q_func_drop 
        # loss = 0.5 * self._diff ** 2 
        loss = 0.5 * T.pow(self._diff, 2)
        self._loss = T.mean(loss)
        self._loss_drop = T.mean(0.5 * self._diff_drop ** 2)
        
        self._params = lasagne.layers.helper.get_all_params(self._model.getCriticNetwork())
        self._actionParams = lasagne.layers.helper.get_all_params(self._model.getActorNetwork())
        self._givens_ = {
            self._model.getStateSymbolicVariable(): self._model.getStates(),
            self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            # self._NotFallen: self._NotFallen_shared
            # self._model.getActionSymbolicVariable(): self._actions_shared,
        }
        self._actGivens = {
            self._model.getStateSymbolicVariable(): self._model.getStates(),
            # self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            # self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            self._model.getActionSymbolicVariable(): self._model.getActions(),
            # self._NotFallen: self._NotFallen_shared,
            self._advantage: self._advantage_shared,
            # self._KL_Weight: self._kl_weight_shared
        }
        
        self._allGivens = {
            self._model.getStateSymbolicVariable(): self._model.getStates(),
            self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            self._model.getActionSymbolicVariable(): self._model.getActions(),
            # self._NotFallen: self._NotFallen_shared,
            self._advantage: self._advantage_shared,
            # self._KL_Weight: self._kl_weight_shared
        }
        
        
        self._critic_regularization = (self._critic_regularization_weight * lasagne.regularization.regularize_network_params(
        self._model.getCriticNetwork(), lasagne.regularization.l2))
        self._actor_regularization = (self._regularization_weight * lasagne.regularization.regularize_network_params(
                self._model.getActorNetwork(), lasagne.regularization.l2))
        self._kl_firstfixed = T.mean(kl(self._q_valsActTarget, self._q_valsActTargetSTD, self._q_valsActA, self._q_valsActASTD, self._action_length))
        # self._actor_regularization = (( self.getSettings()['previous_value_regularization_weight']) * self._kl_firstfixed )
        # self._actor_regularization = (( self._KL_Weight ) * self._kl_firstfixed ) + (10*(self._kl_firstfixed>self.getSettings()['kl_divergence_threshold'])*
        #                                                                              T.square(self._kl_firstfixed-self.getSettings()['kl_divergence_threshold']))
        self._actor_entropy = 0.5 * T.mean((2 * np.pi * self._q_valsActASTD ) )
        # SGD update
        # self._updates_ = lasagne.updates.rmsprop(self._loss + (self._regularization_weight * lasagne.regularization.regularize_network_params(
        # self._model.getCriticNetwork(), lasagne.regularization.l2)), self._params, self._learning_rate, self._rho,
        #                                    self._rms_epsilon)
        self._value_grad = T.grad(self._loss + self._critic_regularization
                                                     , self._params)
        ## Clipping the max gradient
        """
        for x in range(len(self._value_grad)): 
            self._value_grad[x] = T.clip(self._value_grad[x] ,  -0.1, 0.1)
        """
        if (self.getSettings()['optimizer'] == 'rmsprop'):
            print ("Optimizing Value Function with ", self.getSettings()['optimizer'], " method")
            self._updates_ = lasagne.updates.rmsprop(self._value_grad
                                                     , self._params, self._learning_rate, self._rho,
                                           self._rms_epsilon)
        elif (self.getSettings()['optimizer'] == 'momentum'):
            print ("Optimizing Value Function with ", self.getSettings()['optimizer'], " method")
            self._updates_ = lasagne.updates.momentum(self._value_grad
                                                      , self._params, self._critic_learning_rate , momentum=self._rho)
        elif ( self.getSettings()['optimizer'] == 'adam'):
            print ("Optimizing Value Function with ", self.getSettings()['optimizer'], " method")
            self._updates_ = lasagne.updates.adam(self._value_grad
                        , self._params, self._critic_learning_rate , beta1=0.9, beta2=0.9, epsilon=self._rms_epsilon)
        elif ( self.getSettings()['optimizer'] == 'adagrad'):
            print ("Optimizing Value Function with ", self.getSettings()['optimizer'], " method")
            self._updates_ = lasagne.updates.adagrad(self._value_grad
                        , self._params, self._critic_learning_rate, epsilon=self._rms_epsilon)
        else:
            print ("Unknown optimization method: ", self.getSettings()['optimizer'])
            sys.exit(-1)
        ## Need to perform an element wise operation or replicate _diff for this to work properly.
        # self._actDiff = theano.tensor.elemwise.Elemwise(theano.scalar.mul)((self._model.getActionSymbolicVariable() - self._q_valsActA), 
        #                                                                    theano.tensor.tile((self._advantage * (1.0/(1.0-self._discount_factor))), self._action_length)) # Target network does not work well here?
        
        ## advantage = Q(a,s) - V(s) = (r + gamma*V(s')) - V(s) 
        # self._advantage = (((self._model.getRewardSymbolicVariable() + (self._discount_factor * self._q_valsTargetNextState)) * self._NotFallen)) - self._q_func
        
        self._Advantage = self._advantage #  * (1.0/(1.0-self._discount_factor)) ## scale back to same as rewards
        # self._log_prob = loglikelihood(self._model.getActionSymbolicVariable(), self._q_valsActA, self._q_valsActASTD, self._action_length)
        # self._log_prob_target = loglikelihood(self._model.getActionSymbolicVariable(), self._q_valsActTarget, self._q_valsActTargetSTD, self._action_length)
        ### Only change the std
        self._prob = likelihood(self._model.getActionSymbolicVariable(), self._q_valsActTarget, self._q_valsActASTD, self._action_length)
        self._prob_target = likelihood(self._model.getActionSymbolicVariable(), self._q_valsActTarget, self._q_valsActTargetSTD, self._action_length)
        ## This does the sum already
        self._r = (self._prob / self._prob_target)
        self._actLoss_ = theano.tensor.elemwise.Elemwise(theano.scalar.mul)((self._r), self._Advantage)
        ppo_epsilon = self.getSettings()['kl_divergence_threshold']
        self._actLoss_2 = theano.tensor.elemwise.Elemwise(theano.scalar.mul)((theano.tensor.clip(self._r, 1.0 - ppo_epsilon, 1+ppo_epsilon), self._Advantage))
        self._actLoss_ = theano.tensor.minimum((self._actLoss_), (self._actLoss_2))

        self._actLoss = (-1.0 * (T.mean(self._actLoss_) + (self.getSettings()['std_entropy_weight'] * self._actor_entropy))) + self._actor_regularization

        self._policy_grad = T.grad(self._actLoss ,  self._actionParams)
        self._policy_grad = lasagne.updates.total_norm_constraint(self._policy_grad, 5)
        if (self.getSettings()['optimizer'] == 'rmsprop'):
            self._actionUpdates = lasagne.updates.rmsprop(self._policy_grad, self._actionParams, 
                    self._learning_rate , self._rho, self._rms_epsilon)
        elif (self.getSettings()['optimizer'] == 'momentum'):
            self._actionUpdates = lasagne.updates.momentum(self._policy_grad, self._actionParams, 
                    self._learning_rate , momentum=self._rho)
        elif ( self.getSettings()['optimizer'] == 'adam'):
            self._actionUpdates = lasagne.updates.adam(self._policy_grad, self._actionParams, 
                    self._learning_rate , beta1=0.9, beta2=0.999, epsilon=1e-08)
        else:
            print ("Unknown optimization method: ", self.getSettings()['optimizer'])
            
            
        
        if ( ('train_state_encoding' in self.getSettings()) and (self.getSettings()['train_state_encoding'])):
            self._encoded_state = lasagne.layers.get_output(self._model.getEncodeNet(), self._model.getStateSymbolicVariable(), deterministic=True)
            self._encoding_loss = T.mean(T.pow(self._encoded_state - self._model.getStates(), 2))
            self._full_loss = (self._loss + 
                           self._critic_regularization +
                           (-1.0 * self.getSettings()['policy_loss_weight'] * (T.mean(self._actLoss_) + 
                                   (self.getSettings()['std_entropy_weight'] * self._actor_entropy)))
                           + (
                              self._actor_regularization +
                                self._encoding_loss 
                               )
                           )
        else:
            self._full_loss = (
                            self._loss + 
                            self._critic_regularization +
                            (-1.0 * self.getSettings()['policy_loss_weight'] * (
                                        T.mean(self._actLoss_) + 
                                    (self.getSettings()['std_entropy_weight'] * self._actor_entropy)
                                    )
                             ) 
                            + self._actor_regularization
                            )
            
        if ( ('train_state_encoding' in self.getSettings()) and (self.getSettings()['train_state_encoding'])):
            self._encodeParams = lasagne.layers.helper.get_all_params(self._model.getEncodeNet())
            self._all_Params = self._params + self._actionParams + self._encodeParams 
        else:
            # self._all_Params = self._params + self._actionParams[-3:]    
            self._all_Params = self._params + self._actionParams
        print ("Num params: ", len(self._all_Params), " params: ", len(self._params) , " act params: ", len(self._actionParams))
        self._both_grad = T.grad(self._full_loss ,  self._all_Params)
        self._both_grad = lasagne.updates.total_norm_constraint(self._both_grad, 5)
        if (self.getSettings()['optimizer'] == 'rmsprop'):
            self._collectiveUpdates = lasagne.updates.rmsprop(self._both_grad, self._all_Params, 
                    self._learning_rate , self._rho, self._rms_epsilon)
        elif (self.getSettings()['optimizer'] == 'momentum'):
            self._collectiveUpdates = lasagne.updates.momentum(self._both_grad, self._all_Params, 
                    self._learning_rate , momentum=self._rho)
        elif ( self.getSettings()['optimizer'] == 'adam'):
            self._collectiveUpdates = lasagne.updates.adam(self._both_grad, self._all_Params, 
                    self._learning_rate , beta1=0.9, beta2=0.999, epsilon=1e-08)
        else:
            print ("Unknown optimization method: ", self.getSettings()['optimizer'])
            
        
        # actionUpdates = lasagne.updates.rmsprop(T.mean(self._q_funcAct_drop) + 
        #   (self._regularization_weight * lasagne.regularization.regularize_network_params(
        #       self._model.getActorNetwork(), lasagne.regularization.l2)), actionParams, 
        #           self._learning_rate * 0.5 * (-T.sum(actDiff_drop)/float(self._batch_size)), self._rho, self._rms_epsilon)
        self._givens_grad = {
            self._model.getStateSymbolicVariable(): self._model.getStates(),
            # self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            # self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            # self._model.getActionSymbolicVariable(): self._actions_shared,
        }
        
        ### _q_valsA because the predicted state is stored in self._model.getStateSymbolicVariable()
        self._diff_dyna = self._dyna_target - self._q_valsNextState
        # loss = 0.5 * self._diff ** 2 
        loss = 0.5 * T.pow(self._diff_dyna, 2)
        self._loss_dyna = T.mean(loss)
        
        self._dyna_grad = T.grad(self._loss_dyna + self._critic_regularization ,  self._params)
        
        self._givens_dyna = {
            # self._model.getStateSymbolicVariable(): self._model.getStates(),
            self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            # self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            # self._NotFallen: self._NotFallen_shared
            # self._model.getActionSymbolicVariable(): self._actions_shared,
            self._dyna_target: self._dyna_target_shared
        }
        if (self.getSettings()['optimizer'] == 'rmsprop'):
            self._DYNAUpdates = lasagne.updates.rmsprop(self._dyna_grad, self._params, 
                    self._learning_rate , self._rho, self._rms_epsilon)
        elif (self.getSettings()['optimizer'] == 'momentum'):
            self._DYNAUpdates = lasagne.updates.momentum(self._dyna_grad, self._params, 
                    self._learning_rate , momentum=self._rho)
        elif ( self.getSettings()['optimizer'] == 'adam'):
            self._DYNAUpdates = lasagne.updates.adam(self._dyna_grad, self._params, 
                    self._learning_rate , beta1=0.9, beta2=0.999, epsilon=self._rms_epsilon)
        elif ( self.getSettings()['optimizer'] == 'adagrad'):
            self._DYNAUpdates = lasagne.updates.adagrad(self._dyna_grad, self._params, 
                    self._learning_rate, epsilon=self._rms_epsilon)
        else:
            print ("Unknown optimization method: ", self.getSettings()['optimizer'])
        
        ## Bellman error
        self._bellman = self._target - self._q_funcTarget
        
        ## Some cool stuff to backprop action gradients
        
        self._action_grad = T.matrix("Action_Grad")
        self._action_grad.tag.test_value = np.zeros((self._batch_size,self._action_length), dtype=np.dtype(self.getSettings()['float_type']))
        
        self._action_grad_shared = theano.shared(
            np.zeros((self._batch_size, self._action_length),
                      dtype=self.getSettings()['float_type']))
        
        self._action_mean_grads = T.grad(cost=None, wrt=self._actionParams,
                                                            known_grads={self._q_valsActA: self._action_grad_shared}),
        # print ("Action grads: ", self._action_mean_grads[0])
        ## When passing in gradients it needs to be a proper list of gradient expressions
        self._action_mean_grads = list(self._action_mean_grads[0])
        # print ("isinstance(self._action_mean_grads, list): ", isinstance(self._action_mean_grads, list))
        # print ("Action grads: ", self._action_mean_grads)
        self._actionGRADUpdates = lasagne.updates.adagrad(self._action_mean_grads, self._actionParams, 
                    self._learning_rate, epsilon=self._rms_epsilon)
        
        self._actGradGivens = {
            self._model.getStateSymbolicVariable(): self._model.getStates(),
            # self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            # self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            # self._model.getActionSymbolicVariable(): self._model.getActions(),
            # self._NotFallen: self._NotFallen_shared,
            # self._advantage: self._advantage_shared,
            # self._KL_Weight: self._kl_weight_shared
        }
        
        """
        self._get_grad = theano.function([], outputs=T.grad(cost=None, wrt=[self._model._actionInputVar] + self._params,
                                                            known_grads={self._forward: self._fd_grad_target_shared}), 
                                         allow_input_downcast=True, 
                                         givens= {
            self._model.getStateSymbolicVariable() : self._model.getStates(),
            # self._model.getResultStateSymbolicVariable() : self._model.getResultStates(),
            self._model.getActionSymbolicVariable(): self._model.getActions(),
            # self._fd_grad_target : self._fd_grad_target_shared
        })
        """
        MBPG.compile(self)
        
    def compile(self):
        
        #### Stuff for Debugging #####
        #### Stuff for Debugging #####
        self._get_diff = theano.function([], [self._diff], givens=self._givens_)
        self._get_advantage = self._get_diff
        # self._get_advantage = theano.function([], [self._advantage])
        self._get_target = theano.function([], [self._target], givens={
            # self._model.getStateSymbolicVariable(): self._model.getStates(),
            self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            # self._NotFallen: self._NotFallen_shared
            # self._model.getActionSymbolicVariable(): self._actions_shared,
        })
        self._get_critic_regularization = theano.function([], [self._critic_regularization])
        self._get_critic_loss = theano.function([], [self._loss], givens=self._givens_)
        
        self._get_actor_regularization = theano.function([], [self._actor_regularization]
                                                            #givens={self._model.getStateSymbolicVariable(): self._model.getStates(),
                                                                    # self._KL_Weight: self._kl_weight_shared
                                                            #        }
                                                         )
        self._get_actor_entropy = theano.function([], [self.getSettings()['std_entropy_weight'] * self._actor_entropy],
                                                            givens={self._model.getStateSymbolicVariable(): self._model.getStates(),
                                                                    # self._KL_Weight: self._kl_weight_shared
                                                                    }
                                                         )
        self._get_actor_loss = theano.function([], [self._actLoss], givens=self._actGivens)
        # self._get_actor_diff_ = theano.function([], [self._actDiff], givens= self._actGivens)
        """{
            self._model.getStateSymbolicVariable(): self._model.getStates(),
            self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            self._model.getActionSymbolicVariable(): self._model.getActions(),
            self._NotFallen: self._NotFallen_shared
        }) """
        
        self._get_action_diff = theano.function([], [self._actLoss_], givens={
            self._model.getStateSymbolicVariable(): self._model.getStates(),
            # self._model.getResultStateSymbolicVariable(): self._model.getResultStates(),
            # self._model.getRewardSymbolicVariable(): self._model.getRewards(),
            self._model.getActionSymbolicVariable(): self._model.getActions(),
            # self._NotFallen: self._NotFallen_shared,
            self._advantage: self._advantage_shared,
            # self._KL_Weight: self._kl_weight_shared
        })
        
        
        self._train = theano.function([], [self._loss, self._q_func], updates=self._updates_, givens=self._givens_)
        self._trainActor = theano.function([], [self._actLoss, self._q_func_drop], updates=self._actionUpdates, givens=self._actGivens)
        self._trainDyna = theano.function([], [self._loss_dyna], updates=self._DYNAUpdates, givens=self._givens_dyna)
        
        self._trainCollective = theano.function([], [self._full_loss, self._q_func], updates=self._collectiveUpdates, givens=self._allGivens)
        
        self._trainActionGRAD  = theano.function([], [], updates=self._actionGRADUpdates, givens=self._actGradGivens)
        self._q_val = theano.function([], self._q_func,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates()})
        self._val_TargetState = theano.function([], self._q_funcTarget,
                                       givens={self._model.getStateSymbolicVariable(): self._modelTarget.getStates()})
        self._q_valTarget = theano.function([], self._q_funcTarget,
                                       givens={self._model.getStateSymbolicVariable(): self._modelTarget.getStates()})
        self._q_val_drop = theano.function([], self._q_func_drop,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates()})
        self._q_action_drop = theano.function([], self._q_valsActA_drop,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates()})
        self._q_action = theano.function([], self._q_valsActA,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates()})
        self._q_action_std = theano.function([], self._q_valsActASTD,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates()})
        self._get_log_prob = theano.function([], self._prob,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates(),
                                               self._model.getActionSymbolicVariable(): self._model.getActions(),})
        self._get_log_prob_target = theano.function([], self._prob_target,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates(),
                                               self._model.getActionSymbolicVariable(): self._model.getActions(),})
        
        self._q_action_target = theano.function([], self._q_valsActTarget,
                                       givens={self._model.getStateSymbolicVariable(): self._model.getStates()})
        # self._bellman_error_drop = theano.function(inputs=[self._model.getStateSymbolicVariable(), self._model.getRewardSymbolicVariable(), self._model.getResultStateSymbolicVariable()], outputs=self._diff_drop, allow_input_downcast=True)
        self._bellman_error_drop2 = theano.function(inputs=[], outputs=self._diff_drop, allow_input_downcast=True, givens=self._givens_)
        
        # self._bellman_error = theano.function(inputs=[self._model.getStateSymbolicVariable(), self._model.getResultStateSymbolicVariable(), self._model.getRewardSymbolicVariable()], outputs=self._diff, allow_input_downcast=True)
        self._bellman_error2 = theano.function(inputs=[], outputs=self._diff, allow_input_downcast=True, givens=self._givens_)
        self._bellman_errorTarget = theano.function(inputs=[], outputs=self._bellman, allow_input_downcast=True, givens=self._givens_)
        # self._diffs = theano.function(input=[self._model.getStateSymbolicVariable()])
        self._get_grad = theano.function([], outputs=lasagne.updates.get_or_compute_grads(T.mean(self._q_func), [self._model._stateInputVar] + self._params), allow_input_downcast=True, givens=self._givens_grad)
        # self._get_grad2 = theano.gof.graph.inputs(lasagne.updates.rmsprop(loss, params, self._learning_rate, self._rho, self._rms_epsilon))
        
        # self._compute_fisher_vector_product = theano.function([flat_tangent] + args, fvp, **FNOPTS)
        self.kl_divergence = theano.function([], self._kl_firstfixed,
                                             givens={self._model.getStateSymbolicVariable(): self._model.getStates()})
        
    def updateTargetModel(self):
        if (self.getSettings()["print_levels"][self.getSettings()["print_level"]] >= self.getSettings()["print_levels"]['train']):
            print ("Updating target Model")
        """
            Target model updates
        """
        all_paramsA = lasagne.layers.helper.get_all_param_values(self._model.getCriticNetwork())
        all_paramsActA = lasagne.layers.helper.get_all_param_values(self._model.getActorNetwork())
        lasagne.layers.helper.set_all_param_values(self._modelTarget.getCriticNetwork(), all_paramsA)
        lasagne.layers.helper.set_all_param_values(self._modelTarget.getActorNetwork(), all_paramsActA) 
        
    def setData(self, states, actions, rewards, result_states, fallen):
        self._model.setStates(states)
        self._model.setResultStates(result_states)
        self._model.setActions(actions)
        self._model.setRewards(rewards)
        self._modelTarget.setStates(states)
        self._modelTarget.setResultStates(result_states)
        self._modelTarget.setActions(actions)
        self._modelTarget.setRewards(rewards)
        # print ("Falls: ", fallen)
        self._NotFallen_shared.set_value(fallen)
        # diff_ = self.bellman_error(states, actions, rewards, result_states, falls)
        ## Easy fix for computing actor loss
        diff = self._bellman_error2()
        self._advantage_shared.set_value(diff)
        
        # _targets = rewards + (self._discount_factor * self._q_valsTargetNextState )
        
    def trainCritic(self, states, actions, rewards, result_states, falls):
        
        self.setData(states, actions, rewards, result_states, falls)
        # print ("Performing Critic trainning update")
        if (( self._updates % self._weight_update_steps) == 0):
            self.updateTargetModel()
        self._updates += 1
        # print ("Falls:", falls)
        # print ("Ceilinged Rewards: ", np.ceil(rewards))
        # print ("Target Values: ", self._get_target())
        # print ("V Values: ", np.mean(self._q_val()))
        # print ("diff Values: ", np.mean(self._get_diff()))
        # data = np.append(falls, self._get_target()[0], axis=1)
        # print ("Rewards, Falls, Targets:", np.append(rewards, data, axis=1))
        # print ("Rewards, Falls, Targets:", [rewards, falls, self._get_target()])
        # print ("Actions: ", actions)
        loss, _ = self._train()
        # loss, _ = self._trainCollective
        print("Value function loss: ", loss)
        return loss
            
    
    def trainActor(self, states, actions, rewards, result_states, falls, advantage, exp_actions=None, forwardDynamicsModel=None):
        
        self.setData(states, actions, rewards, result_states, falls)
        if (( ('ppo_use_seperate_nets' in self.getSettings())) and
             ( self.getSettings()['ppo_use_seperate_nets'])):
            pass
        else:
            if (( self._updates % self._weight_update_steps) == 0):
                self.updateTargetModel()
            self._updates += 1
            
        if ('use_GAE' in self.getSettings() and ( self.getSettings()['use_GAE'] )):
            # self._advantage_shared.set_value(advantage)
            ## Need to scale the advantage by the discount to help keep things normalized
            if (('normalize_advantage' in self.getSettings()) and self.getSettings()['normalize_advantage']):
                # advantage = advantage * (1.0-self._discount_factor)
                advantage = advantage * (1.0-self._discount_factor) 
            # pass # use given advantage parameter
        else:
            advantage = self._get_advantage()
        self._advantage_shared.set_value(advantage)
        
        if (self.getSettings()["print_levels"][self.getSettings()["print_level"]] >= self.getSettings()["print_levels"]['debug']):
            print("Rewards: ", np.mean(rewards), " std: ", np.std(rewards), " shape: ", np.array(rewards).shape)
            print("Targets: ", np.mean(self._get_target()), " std: ", np.std(self._get_target()))
            print("Falls: ", np.mean(falls), " std: ", np.std(falls))
            # print("values, falls: ", np.concatenate((scale_reward(self._q_val(), self.getRewardBounds()) * (1.0 / (1.0- self.getSettings()['discount_factor'])), falls), axis=1))
            print("values: ", np.mean(scale_reward(self._q_val(), self.getRewardBounds()) * (1.0 / (1.0- self.getSettings()['discount_factor']))),
                   " std: ", np.std(scale_reward(self._q_val(), self.getRewardBounds()) * (1.0 / (1.0- self.getSettings()['discount_factor']))) )
            
        if (self.getSettings()["print_levels"][self.getSettings()["print_level"]] >= self.getSettings()["print_levels"]['train']):
            print("Advantage: ", np.mean(advantage), " std: ", np.std(advantage))
            print("Actions mean:     ", np.mean(actions, axis=0))
            print("Policy mean: ", np.mean(self._q_action(), axis=0))
            # print("Actions std:  ", np.mean(np.sqrt( (np.square(np.abs(actions - np.mean(actions, axis=0))))/1.0), axis=0) )
            print("Actions std:  ", np.std((actions - self._q_action()), axis=0) )
            # print("Actions std:  ", np.std((actions), axis=0) )
            print("Policy   std: ", np.mean(self._q_action_std(), axis=0))
            # print("Policy log prob target: ", np.mean(self._get_log_prob_target(), axis=0))
            print("Actor loss: ", np.mean(self._get_action_diff()))
            print("Actor entropy: ", np.mean(self._get_actor_entropy()))
            # self._get_actor_entropy
            # print("States mean:     ", np.mean(states, axis=0))
            # print("States std:     ", np.std(states, axis=0))
            # print ( "R: ", np.mean(self._get_log_prob()/self._get_log_prob_target()))
            # print ("Actor diff: ", np.mean(np.array(self._get_diff()) / (1.0/(1.0-self._discount_factor))))
            ## Sometimes really HUGE losses appear, occasionally
        if ( not self.getSettings()['use_fixed_std'] ): # whether or not to update the std of policy as well.
            lossActor = np.abs(np.mean(self._get_action_diff()))
            if (lossActor < 1000): 
                if ('ppo_use_seperate_nets' in self.getSettings() and (self.getSettings()['ppo_use_seperate_nets'])):
                    lossActor, _ = self._trainActor()
                else:
                    lossActor, _ = self._trainCollective()
            else:
                print ("**********************Did not train actor this time: expected loss to high, ", lossActor)
            if (self.getSettings()["print_levels"][self.getSettings()["print_level"]] >= self.getSettings()["print_levels"]['train']):
                print("Policy log prob after: ", np.mean(self._get_log_prob(), axis=0))
                # print("KL Divergence: ", np.sum(self.kl_divergence()))
                print("KL Divergence: ", self.kl_divergence())
        
        actions = self.predict_batch(states)
        # print ("actions shape:", actions.shape)
        next_states = forwardDynamicsModel.predict_batch(states, actions)
        # print ("next_states shape: ", next_states.shape)
        next_state_grads = self.getGrads(next_states, alreadyNormed=True)[0]
        # print ("next_state_grads shape: ", next_state_grads.shape)
        action_grads = forwardDynamicsModel.getGrads(states, actions, next_states, v_grad=next_state_grads, alreadyNormed=True)[0]
        # print ( "action_grads shape: ", action_grads.shape)
        
        use_parameter_grad_inversion=True
        self.setData(states, actions, rewards, result_states, falls)
        
        if ( self.getSettings()['train_reward_predictor']):
            reward_grad = forwardDynamicsModel.getRewardGrads(states, actions)[0]
            ## Need to shrink this reward grad down to the same scale as the value function
            reward_grad = np.array(reward_grad, dtype=self.getSettings()['float_type'])
            action_grads = np.array(action_grads, dtype=self.getSettings()['float_type'])
            action_grads =  (reward_grad * (1.0 - self.getSettings()['discount_factor'])) + (action_grads *  self.getSettings()['discount_factor'])
            if (self.getSettings()["print_levels"][self.getSettings()["print_level"]] >= self.getSettings()["print_levels"]['train']):
                print("Reward_Grad Raw: ", reward_grad)
        
        """
        
            From DEEP REINFORCEMENT LEARNING IN PARAMETERIZED ACTION SPACE
            Hausknecht, Matthew and Stone, Peter
            
            actions.shape == action_grads.shape
            
        """
        if ( use_parameter_grad_inversion ):
            # print ("Performing param inversion")
            for i in range(action_grads.shape[0]):
                for j in range(action_grads.shape[1]):
                    if (action_grads[i,j] > 0):
                        inversion = (1.0 - actions[i,j]) / 2.0
                    else:
                        inversion = ( actions[i,j] - (-1.0)) / 2.0
                    action_grads[i,j] = action_grads[i,j] * inversion
        
        
        if (self.getSettings()["print_levels"][self.getSettings()["print_level"]] >= self.getSettings()["print_levels"]['train']):
            # print("Actions mean:     ", np.mean(actions, axis=0))
            print("Policy mean: ", np.mean(self._q_action(), axis=0))
            # print("Actions std:  ", np.mean(np.sqrt( (np.square(np.abs(actions - np.mean(actions, axis=0))))/1.0), axis=0) )
            # print("Actions std:  ", np.std((actions - self._q_action()), axis=0) )
            # print("Actions std:  ", np.std((actions), axis=0) )
            print("Policy std: ", np.mean(self._q_action_std(), axis=0))
            print("Mean Next State Grad grad: ", np.mean(np.fabs(next_state_grads), axis=0), " std ", np.std(next_state_grads, axis=0))
            print("Mean action grad size: ", np.mean(np.fabs(action_grads), axis=0), " std ", np.std(action_grads, axis=0))
        
        ## Set data for gradient
        # self._model.setStates(states)
        # self._modelTarget.setStates(states)
        ## Why the -1.0??
        ## Because the SGD method is always performing MINIMIZATION!!
        if (np.all(np.isfinite(action_grads))): ## Check these are not bad grads...
            self._action_grad_shared.set_value(-1.0*action_grads)
            self._trainActionGRAD()
        return 0
    
    def trainDyna(self, predicted_states, actions, rewards, result_states, falls):
        """
            Performs a DYNA type update
            Because I am using target network a direct DYNA update does nothing. 
            The gradients are not calculated for the target network.
            L(\theta) = (r + V(s'|\theta')) - V(s|\theta))
            Instead what is done is this
            L(\theta) = V(s_1|\theta')) - V(s_2|\theta))
            Where s1 comes from the simulation and s2 is a predicted and noisey value from an fd model
            Parameters
            ----------
            predicted_states : predicted states, s_1
            
            actions : list of actions
                
            rewards : rewards for taking action a_i
            
            result_states : simulated states, s_2
            
            falls: list of flags for whether or not the character fell
            Returns
            -------
            
            loss: the loss for the DYNA type update

        """
        self.setData( result_states, actions, rewards, predicted_states, falls)
        ## Get the estimated value for the true next state
        values = self._val_TargetState()
        # print ("Dyna values: ", values)
        self._dyna_target_shared.set_value(values)
        dyna_loss = self._trainDyna()
        return dyna_loss[0]
    
    
    def train(self, states, actions, rewards, result_states, falls):
        loss = self.trainCritic(states, actions, rewards, result_states, falls)
        lossActor = self.trainActor(states, actions, rewards, result_states, falls)
        return loss
    
    