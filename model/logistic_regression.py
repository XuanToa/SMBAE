import theano
from theano import tensor as T
import numpy as np
import load_data


def floatX(State):
    return np.asarray(State, dtype=theano.config.floatX)

def init_weights(shape):
    return theano.shared(floatX(np.random.randn(*shape) * 0.1))

class RLLogisticRegression(object):
    """Reinforcement Learning based Logistic regression model

    The logistic regression is fully described by a weight matrix :math:`W`
    and bias vector :math:`b`. Value function approximation is done by projecting data
    points onto a set of hyperplanes, the distance to which is used to
    determine a action value.
    """

    def __init__(self, input, n_in, n_out):
        """ Initialize the parameters of the logistic regression

        :type input: theano.tensor.TensorType
        :param input: symbolic variable that describes the input of the
                      architecture (one minibatch)

        :type n_in: int
        :param n_in: number of input units, the dimension of the space in
                     which the datapoints lie

        :type n_out: int
        :param n_out: number of output units, the dimension of the space in
                      which the labels lie

        """
        
        self._w = init_weights((n_in, n_out))
        self._w_old = init_weights((n_in, n_out))
        print "Initial W " + str(self._w.get_value()) 
        # (n_out,) ,) used so that it can be added as row or column
        self._b = init_weights((n_out,))
        self._b_old = init_weights((n_out,))
        
        # learning rate for gradient descent updates.
        self._learning_rate = 0.01
        # future discount 
        self._discount_factor= 0.8
        self._weight_update_steps=2000
        self._updates=0
        
        # data types for model
        State = T.fmatrix()
        ResultState = T.fmatrix()
        Reward = T.fmatrix()
        # Q_val = T.fmatrix()
        
        model = T.nnet.sigmoid(T.dot(State, self._w) + self._b.reshape((1, -1)))
        self._model = theano.function(inputs=[State], outputs=model, allow_input_downcast=True)
        
        q_val = self.model(State)
        action_pred = T.argmax(q_val, axis=1)
        
        # bellman error, delta error
        delta = ((Reward + (self._discount_factor * T.max(self.targetModel(ResultState), axis=1, keepdims=True)) ) - T.max(self.model(State), axis=1,  keepdims=True))
        # total bellman cost 
        # Squaring is important so error do not cancel each other out.
        # mean is used instead of sum as it is more independent of parameter scale
        bellman_cost = T.mean(0.5 *  ((delta) ** 2 ) )
        
        # Compute gradients w.r.t. model parameters
        gradient = T.grad(cost=bellman_cost, wrt=self._w)
        gradient_b = T.grad(cost=bellman_cost, wrt=self._b)
        
        """
            Updates to apply to parameters
            Performing gradient descent, want to add steps in the negative direction of 
            gradient.
        """
        update = [[self._w, self._w + (-gradient * self._learning_rate)],
                  [self._b, self._b + (-gradient_b * self._learning_rate)]]
        
        # This function performs one training step and update
        self._train = theano.function(inputs=[State, Reward, ResultState], outputs=bellman_cost, updates=update, allow_input_downcast=True)
        # Used to get to predicted actions to select
        self._predict = theano.function(inputs=[State], outputs=action_pred, allow_input_downcast=True)
        self._q_values = theano.function(inputs=[State], outputs=q_val, allow_input_downcast=True)
        self._bellman_error = theano.function(inputs=[State, Reward, ResultState], outputs=delta, allow_input_downcast=True)
        

    def model(self, State):
        # return self._model(State)
        return T.nnet.sigmoid(T.dot(State, self._w) + self._b)
        # return (T.dot(State, self._w) + self._b.reshape((1, -1)))
        
    def targetModel(self, State):
        # return self._model(State)
        return T.nnet.sigmoid(T.dot(State, self._w_old) + self._b_old)
        # return (T.dot(State, self._w) + self._b.reshape((1, -1)))
    
    def updateTargetModel(self):
        print "Updating target Model"
        self._w_old = self._w 
        self._b_old = self._b
        
    def train(self, state, reward, result_state):
        if (( self._updates % self._weight_update_steps) == 0):
            self.updateTargetModel()
        self._updates += 1
        return self._train(state, reward, result_state)
    
    def predict(self, state):
        return self._predict(state)
    def q_values(self, state):
        return self._q_values(state)
    def bellman_error(self, state, reward, result_state):
        return self._bellman_error(state, reward, result_state)
    

if __name__ == "__main__":

    dataset = "controllerTuples.json"
    states, actions, result_states, rewards = load_data.load_data(dataset)
    
    classifier = RLLogisticRegression(states, n_in=9, n_out=9)
    best_error=10000000.0
    
    print "Initial Model: " + str(classifier._model(states).shape)
    print "Initial Model: " + str(np.max(classifier._model(states), axis=1, keepdims=True).shape)
    for i in range(20000):
        for start, end in zip(range(0, len(states), 128), range(128, len(states), 128)):
            # cost = train(states[start:end], rewards[start:end], result_states[start:end])
            _states = states[start:end]
            _rewards = rewards[start:end]
            _result_states = result_states[start:end]
            """
            print _states.shape
            print _rewards.shape
            print _result_states.shape
            """
            cost = classifier.train(_states, _rewards, _result_states)
            # print "Cost: " + str(cost)
        if i % 100 == 0: 
            print ""
            error = classifier.bellman_error(states, rewards, result_states)
            error = np.mean(np.fabs(error))
            print "Iteration: " + str(i) + " Cost: " + str(cost) + " Bellman Error: " + str(error)
            print classifier.q_values(states)[:1]
        # print i, np.mean(np.argmax(q_val, axis=1) == predict(states))
        error = classifier.bellman_error(states, rewards, result_states)
        error = np.mean(np.fabs(error))
        # print "Iteration: " + str(i) + " Cost: " + str(cost) + " Bellman Error: " + str(error)
        if error < best_error:
                # print "Saving better model"
                # load_data.save_model(classifier)
                best_error=error
        
    # save the best model
    load_data.save_model(classifier)
    
    model = load_data.load_model()
    
    print (model.predict(states)[:1000])
    print model._w.get_value()
    print model.q_values(states)[:50]
