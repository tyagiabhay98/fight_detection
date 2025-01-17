# For Youtube Download.
import io 
from pytube import YouTube
from IPython.display import HTML
from base64 import b64encode
from datetime import datetime

import os
import cv2
import time
import copy
import glob
import torch
import argparse
import statistics
import threading
import torchvision
import numpy as np
import pandas as pd
import torch.nn as nn
from moviepy.editor import *
import albumentations as A
from collections import deque
#from google.colab.patches import cv2_imshow

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
DATASET_DIR = '/content/Fight_Detection_From_Surveillance_Cameras-PyTorch_Project/dataset'
CLASSES_LIST = ['fight','noFight']
SEQUENCE_LENGTH = 16
predicted_class_name = ""

# Define the transforms
def transform_():
    transform = A.Compose(
    [A.Resize(128, 171, always_apply=True),A.CenterCrop(112, 112, always_apply=True),
     A.Normalize(mean = [0.43216, 0.394666, 0.37645],std = [0.22803, 0.22145, 0.216989], always_apply=True)]
     )
    return transform


def frames_extraction(video_path,SEQUENCE_LENGTH):
    '''
    This function will extract the required frames from a video after resizing and normalizing them.
    Args:
        video_path: The path of the video in the disk, whose frames are to be extracted.
        SEQUENCE_LENGTH: TThe number of Frames we want.
    Returns:
        frames_list: A list containing the resized and normalized frames of the video.
    '''

    # Declare a list to store video frames.
    frames_list = []
    
    # Read the Video File using the VideoCapture object.
    video_reader = cv2.VideoCapture(video_path)

    # Get the total number of frames in the video.
    video_frames_count = int(video_reader.get(cv2.CAP_PROP_FRAME_COUNT))

    # Calculate the the interval after which frames will be added to the list.
    skip_frames_window = max(int(video_frames_count/SEQUENCE_LENGTH), 1)

    transform= transform_()

    # Iterate through the Video Frames.
    for frame_counter in range(SEQUENCE_LENGTH):

        # Set the current frame position of the video.
        video_reader.set(cv2.CAP_PROP_POS_FRAMES, frame_counter * skip_frames_window)

        # Reading the frame from the video. 
        success, frame = video_reader.read() 

        # Check if Video frame is not successfully read then break the loop
        if not success:
            break

        image = frame.copy()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = transform(image=frame)['image']
        
        # Append the normalized frame into the frames list
        frames_list.append(frame)
    
    # Release the VideoCapture object. 
    video_reader.release()

    # Return the frames list.
    return frames_list


def create_dataset(DATASET_DIR,CLASSES_LIST,SEQUENCE_LENGTH):
    '''
    This function will extract the data of the selected classes and create the required dataset.
    Returns:
        features:          A list containing the extracted frames of the videos.
        labels:            A list containing the indexes of the classes associated with the videos.
    '''

    # Declared Empty Lists to store the features and labels.
    features = []
    labels = []
    
    # Iterating through all the classes mentioned in the classes list
    for class_index, class_name in enumerate(CLASSES_LIST):
        
        # Display the name of the class whose data is being extracted.
        print(f'Extracting Data of Class: {class_name}')
        
        # Get the list of video files present in the specific class name directory.
        files_list = os.listdir(os.path.join(DATASET_DIR, class_name))
        
        # Iterate through all the files present in the files list.
        for file_name in files_list:
            
            # Get the complete video path.
            video_file_path = os.path.join(DATASET_DIR, class_name, file_name)

            # Extract the frames of the video file.
            frames = frames_extraction(video_file_path,SEQUENCE_LENGTH)

            # Check if the extracted frames are equal to the SEQUENCE_LENGTH specified above.
            # So ignore the vides having frames less than the SEQUENCE_LENGTH.
            if len(frames) == SEQUENCE_LENGTH:
                # Append the data to their repective lists.
                input_frames = np.array(frames)
                
                # transpose to get [3, num_clips, height, width]
                input_frames = np.transpose(input_frames, (3,0, 1, 2))

                # convert the Frames & Labels to tensor
                input_frames = torch.tensor(input_frames, dtype=torch.float32)
                label = torch.tensor(int(class_index))

                # Append the data to their repective lists and Stack them as Tensor.
                features.append(input_frames) # append to list
                labels.append(label) # append to list
               

              
    # Return the frames, class index, and video file path.
    return  torch.stack(features), torch.stack(labels)

# Function To Train the Model From Pytorch Documentation
def train_model(device,model, dataloaders, criterion, optimizer, num_epochs=25, is_inception=False):
    since = time.time()

    val_acc_history = []

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(num_epochs):
        print('Epoch {}/{}'.format(epoch, num_epochs - 1))
        print('-' * 10)

        # Each epoch has a training and validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()  # Set model to training mode
            else:
                model.eval()   # Set model to evaluate mode

            running_loss = 0.0
            running_corrects = 0

            # Iterate over data.
            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(device)
                labels = labels.to(device)

                # zero the parameter gradients
                optimizer.zero_grad()

                # forward
                # track history if only in train
                with torch.set_grad_enabled(phase == 'train'):
                    # Get model outputs and calculate loss
                    # Special case for inception because in training it has an auxiliary output. In train
                    #   mode we calculate the loss by summing the final output and the auxiliary output
                    #   but in testing we only consider the final output.
                    if is_inception and phase == 'train':
                        # From https://discuss.pytorch.org/t/how-to-optimize-inception-model-with-auxiliary-classifiers/7958
                        outputs, aux_outputs = model(inputs)
                        loss1 = criterion(outputs, labels)
                        loss2 = criterion(aux_outputs, labels)
                        loss = loss1 + 0.4*loss2
                    else:
                        outputs = model(inputs)
                        loss = criterion(outputs, labels)

                    _, preds = torch.max(outputs, 1)

                    # backward + optimize only if in training phase
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                # statistics
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / len(dataloaders[phase].dataset)
            epoch_acc = running_corrects.double() / len(dataloaders[phase].dataset)

            print('{} Loss: {:.4f} Acc: {:.4f}'.format(phase, epoch_loss, epoch_acc))

            # deep copy the model
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())
            if phase == 'val':
                val_acc_history.append(epoch_acc)

        print()

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(time_elapsed // 60, time_elapsed % 60))
    print('Best val Acc: {:4f}'.format(best_acc))

    # load best model weights
    model.load_state_dict(best_model_wts)
    return model, val_acc_history

def loadModel(modelPath):
  PATH=modelPath
  model_ft = torchvision.models.video.mc3_18(pretrained=True, progress=False)
  num_ftrs = model_ft.fc.in_features         #in_features
  model_ft.fc = torch.nn.Linear(num_ftrs, 2) #nn.Linear(in_features, out_features)
  model_ft.load_state_dict(torch.load(PATH,map_location=torch.device(device)))
  model_ft.to(device)
  model_ft.eval()
  return model_ft

def PredTopKClass(k, clips, model):
  with torch.no_grad(): # we do not want to backprop any gradients

      input_frames = np.array(clips)
      
      # add an extra dimension        
      input_frames = np.expand_dims(input_frames, axis=0)

      # transpose to get [1, 3, num_clips, height, width]
      input_frames = np.transpose(input_frames, (0, 4, 1, 2, 3))

      # convert the frames to tensor
      input_frames = torch.tensor(input_frames, dtype=torch.float32)
      input_frames = input_frames.to(device)

      # forward pass to get the predictions
      outputs = model(input_frames)

      # get the prediction index
      soft_max = torch.nn.Softmax(dim=1)  
      probs = soft_max(outputs.data) 
      prob, indices = torch.topk(probs, k)

  Top_k = indices[0]
  Classes_nameTop_k=[CLASSES_LIST[item].strip() for item in Top_k]
  ProbTop_k=prob[0].tolist()
  ProbTop_k = [round(elem, 5) for elem in ProbTop_k]
  return Classes_nameTop_k[0]    #list(zip(Classes_nameTop_k,ProbTop_k))


def PredTopKProb(k,clips,model):
  with torch.no_grad(): # we do not want to backprop any gradients

      input_frames = np.array(clips)
      
      # add an extra dimension        
      input_frames = np.expand_dims(input_frames, axis=0)

      # transpose to get [1, 3, num_clips, height, width]
      input_frames = np.transpose(input_frames, (0, 4, 1, 2, 3))

      # convert the frames to tensor
      input_frames = torch.tensor(input_frames, dtype=torch.float32)
      input_frames = input_frames.to(device)

      # forward pass to get the predictions
      outputs = model(input_frames)

      # get the prediction index
      soft_max = torch.nn.Softmax(dim=1)  
      probs = soft_max(outputs.data) 
      prob, indices = torch.topk(probs, k)

  Top_k = indices[0]
  Classes_nameTop_k=[CLASSES_LIST[item].strip() for item in Top_k]
  ProbTop_k=prob[0].tolist()
  ProbTop_k = [round(elem, 5) for elem in ProbTop_k]
  return list(zip(Classes_nameTop_k,ProbTop_k))

def downloadYouTube(videourl, path):

    yt = YouTube(videourl)
    yt = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
    if not os.path.exists(path):
        os.makedirs(path)
    yt.download(path)

def show_video(file_name, width=640):
  # show resulting deepsort video
  mp4 = open(file_name,'rb').read()
  data_url = "data:video/mp4;base64," + b64encode(mp4).decode()
  return HTML("""
  <video width="{0}" controls>
        <source src="{1}" type="video/mp4">
  </video>
  """.format(width, data_url))

def FightInference(video_path,model,SEQUENCE_LENGTH=64):
  clips = frames_extraction(video_path,SEQUENCE_LENGTH)
  print(PredTopKClass(1,clips, model))
  print(PredTopKProb(2,clips, model))
  return "***********"


def FightInference_Time(video_path,model,SEQUENCE_LENGTH=64):
  start_time = time.time()
  clips = frames_extraction(video_path,SEQUENCE_LENGTH)
  class_=PredTopKClass(1,clips,model)
  elapsed = time.time() - start_time
  print("time is:",elapsed)
  return class_




def predict_on_video(video_file_path, output_folder_path, model, SEQUENCE_LENGTH,skip=2,showInfo=False):
    '''
    This function will perform action recognition on a video using the LRCN model.
    Args:
    video_file_path:  The path of the video stored in the disk on which the action recognition is to be performed.
    output_file_path: The path where the ouput video with the predicted action being performed overlayed will be stored.
    SEQUENCE_LENGTH:  The fixed number of frames of a video that can be passed to the model as one sequence.
    '''

    # Initialize the VideoCapture object to read from the video file.
    video_reader = cv2.VideoCapture(video_file_path)

    # Get the width, height and fps of the video.
    original_video_width = int(video_reader.get(cv2.CAP_PROP_FRAME_WIDTH))
    original_video_height = int(video_reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = video_reader.get(cv2.CAP_PROP_FPS)
    print(f"Video FPS: {fps}")

    # check if the output folder exits or not
    # if it does'nt, then make the folder
    alert_folder_check(output_folder_path)

    # output video path inside the output folder
    output_video_path = f"{output_folder_path}/Output_video.mp4"

    # Initialize the VideoWriter Object to store the output video in the disk.
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(output_video_path, fourcc, 
                                   video_reader.get(cv2.CAP_PROP_FPS), (original_video_width, original_video_height))

    # Declare a queue to store video frames.
    frames_queue = deque(maxlen = SEQUENCE_LENGTH)
    transform= transform_()
    # Initialize a variable to store the predicted action being performed in the video.
    predicted_class_name = ''

    # Iterate until the video is accessed successfully.
    counter=0
    s_no = 1
    while video_reader.isOpened():

        # Read the frame.
        ok, frame = video_reader.read()
        
        # Check if frame is not read properly then break the loop.
        if not ok:
            break

        image = frame.copy()
        framee = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        framee = transform(image=framee)['image']
        if counter % skip==0:
          # Appending the pre-processed frame into the frames list.
          frames_queue.append(framee)
         
        # changing the predicted class name to blank before the prediction
        # this will make sure to only print the label on the first frame of the bunch
        # predicted_class_name = ''

        # Check if the number of frames in the queue are equal to the fixed sequence length.
        if len(frames_queue) == SEQUENCE_LENGTH:
            predicted_class_name= PredTopKClass(1,frames_queue, model)
            if showInfo:
                print(predicted_class_name)

            # checking if the bunch has "fight" as the predicted class 
            if predicted_class_name=="fight":

                # print the label on the last frame
                cv2.putText(frame, predicted_class_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

                # save the last frame where "fight" label is detected
                # and also add the timestamp and other info in the cvs file
                save_alert_image_csv(frame, s_no, output_folder_path)
            
            # reset the queue
            frames_queue = deque(maxlen = SEQUENCE_LENGTH)
    
        # Write predicted class name on top of the frame.
        if predicted_class_name=="fight":
            cv2.putText(frame, predicted_class_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

        # uncomment the below line if we want to print "no fight" label on the frames
        # else:
        #     cv2.putText(frame, predicted_class_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        counter+=1
        
        # Write The frame into the disk using the VideoWriter Object.
        video_writer.write(frame)
        # time.sleep(2)
    if showInfo:
        print(f"Counter: {counter}")
    # Release the VideoCapture and VideoWriter objects.
    video_reader.release()
    video_writer.release()

def alert_folder_check(path_):
    '''
    This function will perform a check if the folder path mentioned exists or not and if it does not the make the
    folder.
    Args:
    path_:  The path of the folder stored in the disk on where the output is supposed to be saved.
    '''

    # Check if the folder exists, and if not, create it
    if not os.path.exists(path_):
        os.makedirs(path_)
        print(f"Folder '{path_}' created.")
    else:
        print(f"Folder '{path_}' already exists.")
        # pass

def save_alert_image_csv(frame, s_no, path_):
    '''
    This function will save the alert images in a folder and save the alert info in a csv file in the alert folder.
    Args:
    frame: The alert frame which on which alert is raised.
    s_no: The counter to serialise the alerts in the csv file.
    path_:  The path of the folder stored in the disk on where the output is supposed to be saved.
    '''

    # get the current time 
    now = datetime.now()
    timestamp = now.strftime("%Y-%B-%d_%H-%M-%S.%f")
    
    # Alert Image
    # image path
    image_path = f"{path_}/{timestamp}.jpg"

    # Save the image
    cv2.imwrite(image_path, frame)

    # CSV File
    # csv file path
    csv_file_path = f"{path_}/Report.csv"

    # column details to save
    # serial no, alert image name, time stamp and detection in a csv file
    columns = ["S_No", "Image_Name", "Time_stamp", "Feature"]

    try:
        # Try to read the existing CSV file into a DataFrame
        if os.path.isfile(csv_file_path):
            df = pd.read_csv(csv_file_path)
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        # If the file is not found, create a new DataFrame with the specified columns
        df = pd.DataFrame(columns=columns)

    # save the details in the csv column
    new_data = {"S_No": s_no, "Image_Name": timestamp, "Time_stamp": timestamp, "Feature": "Fight"}

    # increase the serial number counter
    s_no+=1

    # Convert new_data to a DataFrame
    new_data_df = pd.DataFrame([new_data])

    # Concatenate the new data with the existing DataFrame
    df = pd.concat([df, new_data_df], ignore_index=True)

    # Save the updated DataFrame back to the CSV file
    df.to_csv(csv_file_path, index=False)

def showIference(model, sequence,skip,input_video_file_path,output_video_file_path,showInfo):
    # Perform Accident Detection on the Test Video.
    predict_on_video(input_video_file_path, output_video_file_path, model,sequence,skip,showInfo)
    return output_video_file_path

def Fight_PipeLine(modelPath,inputPath,seq,skip,outputPath,showInfo=False):
    model = loadModel(modelPath)
    # Perform Accident Detection on the Test Video.
    predict_on_video(inputPath, outputPath, model,seq,skip,showInfo)
    return outputPath

def streaming_framesInference(frames, model):
    clips = []
    transform = transform_()
    for frame in frames:
        image = frame.copy()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = transform(image=frame)['image']

        # Append the normalized frame into the frames list
        clips.append(frame)
    first = PredTopKClass(1, clips, model)
    print(first)
    print(PredTopKProb(2, clips, model))
    return first


def streaming_predict(frames, model):
    prediction = streaming_framesInference(frames, model)
    global predicted_class_name
    predicted_class_name = prediction


def start_streaming(model,streamingPath):
    video = cv2.VideoCapture(streamingPath)
    l = []
    last_time = time.time() - 3
    while True:
        _, frame = video.read()
        if last_time+2.5 < time.time():
            l.append(frame)
        if len(l) == 16:
            last_time = time.time()
            x = threading.Thread(target=streaming_predict, args=(l,model))
            x.start()
            l = []
        if predicted_class_name == "fight":
            cv2.putText(frame, predicted_class_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
        else:
            cv2.putText(frame, predicted_class_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("RTSP", frame)
        k = cv2.waitKey(1)
        if k == ord('q'):
            break

    video.release()
    cv2.destroyAllWindows()

# def predict_on_video(video_file_path, output_file_path, CLASSES_LIST, model, device,T=0.25, SEQUENCE_LENGTH=64):
#     '''
#     This function will perform action recognition on a video using the LRCN model.
#     Args:
#     video_file_path:  The path of the video stored in the disk on which the action recognition is to be performed.
#     output_file_path: The path where the ouput video with the predicted action being performed overlayed will be stored.
#     SEQUENCE_LENGTH:  The fixed number of frames of a video that can be passed to the model as one sequence.
#     '''

#     # Initialize the VideoCapture object to read from the video file.
#     video_reader = cv2.VideoCapture(video_file_path)

#     # Get the width and height of the video.
#     original_video_width = int(video_reader.get(cv2.CAP_PROP_FRAME_WIDTH))
#     original_video_height = int(video_reader.get(cv2.CAP_PROP_FRAME_HEIGHT))

#     # Initialize the VideoWriter Object to store the output video in the disk.
#     video_writer = cv2.VideoWriter(output_file_path, cv2.VideoWriter_fourcc('M', 'P', '4', 'V'), 
#                                    video_reader.get(cv2.CAP_PROP_FPS), (original_video_width, original_video_height))

#     # Declare a queue to store video frames.
#     frames_queue = deque(maxlen = SEQUENCE_LENGTH)
#     transform= transform_()
#     predicted_class_name=''
#     start_time_=time.time()
#     # Iterate until the video is accessed successfully.
#     while video_reader.isOpened():
        
#         # Read the frame.
#         ok, frame = video_reader.read() 
        
#         # Check if frame is not read properly then break the loop.
#         if not ok:
#             break
#         if time.time() >= start_time_+T:
#             image = frame.copy()
#             framee = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#             framee = transform(image=framee)['image']
            
#             # Appending the pre-processed frame into the frames list.
#             frames_queue.append(framee)
            
#         # Check if the number of frames in the queue are equal to the fixed sequence length.
#         if len(frames_queue) == SEQUENCE_LENGTH:
#           predicted_class_name= PredTopKClass(1,frames_queue, CLASSES_LIST, model, device)
          
#         # Write predicted class name on top of the frame.
#         if predicted_class_name=="fight":
#           cv2.putText(frame, predicted_class_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
#         else:
#           cv2.putText(frame, predicted_class_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
#         # Write The frame into the disk using the VideoWriter Object.
#         video_writer.write(frame)
        
#     # Release the VideoCapture and VideoWriter objects.
#     video_reader.release()
#     video_writer.release()