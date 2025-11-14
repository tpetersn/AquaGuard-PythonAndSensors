import pyaudio, numpy as np
from collections import deque
import tensorflow as tf
import tensorflow_hub as hub
import csv
import noisereduce as nr

print("Code Starting from here -->", "\n")
##model set up part
#download the model
model = hub.load('https://www.kaggle.com/models/google/yamnet/TensorFlow2/yamnet/1')

#get the class map (labels) path
class_map_path = model.class_map_path().numpy() 

#Load and return the list of all class labels from provided CSV file path
def class_names_from_csv(class_map_csv_text):
  class_names = []
  with tf.io.gfile.GFile(class_map_csv_text) as csvfile:  # Open the CSV file with given path
    reader = csv.DictReader(csvfile)
    for row in reader:                                            # Iterate through each row in the CSV file
      class_names.append(row['display_name'])   #append the display_name column value to class_names list

  return class_names

class_map_path = model.class_map_path().numpy()
class_names = class_names_from_csv(class_map_path)  #This list contains all 521 class labels used by YAMNet

##audio input set up part
# audio stream parameters
RATE = 16000
CHUNK = 320            # 20 ms
WIN_CHUNKS = 48        # 0.96 s
HOP_CHUNKS = 24        # 0.48 s


# open PyAudio stream at 16 kHz mono, continuous read on microphone input
stream = pyaudio.PyAudio().open(format=pyaudio.paInt16,
                                  channels=1,
                                  rate=RATE,
                                  input=True,
                                  frames_per_buffer=CHUNK)
# buffer to hold audio chunks
buf = deque(maxlen=WIN_CHUNKS)

# counter for hop size
hop_counter = 0

# continuous read loop
while True:
    data = stream.read(CHUNK)                 # bytes
    buf.append(np.frombuffer(data, np.int16)) # int16 array
    hop_counter += 1

    if len(buf) == WIN_CHUNKS and hop_counter >= HOP_CHUNKS:
        hop_counter = 0
        win = np.concatenate(list(buf))             # int16, length 15360
        wav = (win.astype(np.float64) / 32768.0)    # convert to float64  and normalize to range of [-1, 1]
        print("recorded clip info: ", "shape: ", wav.shape, "type: ", wav.dtype)
        print("Type:", type(wav))

        # feed wav to YAMNet from here
        # --- Apply noise reduction ---
        clean_signal = nr.reduce_noise(y=wav, 
                               sr=16000, 
                               stationary=False)
        # --------------------------------

        # Run the model, get scores, embeddings, and spectrogram
        scores, embeddings, spectrogram = model(clean_signal)  
        scores_np = scores.numpy()  
        spectrogram_np = spectrogram.numpy()
        inferred_class = class_names[scores_np.mean(axis=0).argmax()] #get the class with highest mean score of all frames
        # get top 5 classes with highest mean scores
        top_five_indices = scores_np.mean(axis=0).argsort()[-5:][::-1]
        print(f'The main sound is: {inferred_class}')
        print(f'Top 5 sounds are: {[class_names[i] for i in top_five_indices]}')

