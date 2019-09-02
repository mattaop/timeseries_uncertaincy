import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error
import keras.backend as K
from keras import Model, Sequential
from keras.layers import Dense, Input, concatenate
from src.utility.concrete_dropout import ConcreteDropout
from src.preparation.generate_data import generate_sine_data
from src.preparation.load_data import load_raw_data


def train_test_split(data, n_test):
    return data[:-n_test], data[-n_test:]


def series_to_supervised(data, n_in=100, n_out=1):
    df = pd.DataFrame(data)
    cols = list()
    for i in range(n_in, 0, -1):
        cols.append(df.shift(i))
    for i in range(0, n_out):
        cols.append(df.shift(-i))
    agg = pd.concat(cols, axis=1)
    agg.dropna(inplace=True)
    return agg.values


def model_fit(train, config):
    # unpack config
    n_input, n_nodes, n_epochs, n_batch = config
    l = 1e-4
    wd = l ** 2. / len(train)
    dd = 2. / len(train)
    # prepare data
    data = series_to_supervised(train, n_in=n_input)
    train_x, train_y = data[:, :-1], data[:, -1]
    # define model
    inp = Input(shape=(n_input,))
    x = ConcreteDropout(Dense(n_nodes, activation='relu'), weight_regularizer=wd, dropout_regularizer=dd)(x)
    x = Dense(1)(x)
    mean = ConcreteDropout(Dense(1), weight_regularizer=wd, dropout_regularizer=dd)(x)
    log_var = ConcreteDropout(Dense(1), weight_regularizer=wd, dropout_regularizer=dd)(x)
    out = concatenate([mean, log_var])
    model = Model(inp, out)

    def heteroscedastic_loss(true, pred):
        mean = pred[:, :D]
        log_var = pred[:, D:]
        precision = K.exp(-log_var)
        return K.sum(precision * (true - mean) ** 2. + log_var, -1)

    model.compile(optimizer='adam', loss=heteroscedastic_loss)
    assert len(model.layers[1].trainable_weights) == 3  # kernel, bias, and dropout prob
    assert len(model.losses) == 5  # a loss for each Concrete Dropout layer
    hist = model.fit(train_x, train_y, nb_epoch=n_epochs, batch_size=n_batch, verbose=0)
    loss = hist.history['loss'][-1]
    return model, -0.5*loss


# forecast with a pre-fit model
def model_predict(model, history, config):
    # unpack config
    n_input, _, _, _ = config
    # prepare data
    x_input = np.array(history[-n_input:]).reshape(1, n_input)
    # forecast
    yhat = model.predict(x_input, verbose=0)
    return yhat[0]


# root mean squared error or rmse
def measure_rmse(actual, predicted):
    return np.sqrt(mean_squared_error(actual, predicted))


# walk-forward validation for univariate data
def walk_forward_validation(data, n_test, cfg):
    predictions = list()
    train, test = train_test_split(data, n_test)
    model = model_fit(train, cfg)
    history = [x for x in train]
    # step over each time-step in the test set
    for i in range(len(test)):
        # fit model and make forecast for history
        yhat = model_predict(model, history, cfg)
        # store forecast in list of predictions
        predictions.append(yhat)
        # add actual observation to history for the next loop
        history.append(test[i])
    # estimate prediction error
    error = measure_rmse(test, predictions)
    print(' > %.3f' % error)

    # plot predictions
    x = np.linspace(1, len(np.concatenate((train, predictions), axis=None)), len(np.concatenate((train, predictions), axis=None)))
    plt.plot(x, np.concatenate((train, test), axis=None))
    plt.plot(x, np.concatenate((train, predictions), axis=None))
    plt.show()
    return error


# repeat evaluation of a config
def repeat_evaluate(data, config, n_test, n_repeats=30):
    # fit and evaluate the model n times
    scores = [walk_forward_validation(data, n_test, config) for _ in range(n_repeats)]
    return scores


def summarize_scores(name, scores):
    # print a summary
    scores_m, score_std = np.mean(scores), np.std(scores)
    print('%s: %.3f RMSE (+/- %.3f)' % (name, scores_m, score_std))
    # box and whisker plot
    plt.boxplot(scores)
    plt.show()


df = generate_sine_data()
# df = load_raw_data()
df.dropna(axis=1, how='all', inplace=True)
plt.plot(df[['x']], df[['y']])
plt.show()

df = df[['y']].values

# df = df[['V3']].values
# data split
n_test = 12
# define config
config = [24, 500, 100, 100]
# grid search
scores = repeat_evaluate(df, config, n_test)
# summarize scores
summarize_scores('mlp', scores)