Audio File Organizer

Problem Statement

Information heavy audio files are hard to manage. Whether they are recorded lectures, presentations, talks, or meeting minutes, there is no easy way to organize them by hand. One audio file might contain vital information that you can only get if you listen to it all the way through. Or you might want to reference a section of the file, and listen to the surrounding context or tone of voice. This is the problem my project will aim to solve.

This system will input audio files as .mp3 or .wav. It will also support video files with .mp4. These will be uploaded to the server where they can be processed. After a file is processed, it will post the results to the user’s account where they can view specific information about their media files, and have them individually organized. The result of each file processed will output the attached file, along with specific information attached to the file. This would include the main topic, sub-topics, key time stamps, and a list of “truth statements” that were included in the file.

Inputs/Outputs

Input: .mp3, .wav, .mp4

Output:
Media file
Main topic
Sub-topics
Key timestamps
List of truth statements

An AI model is appropriate here to transcribe the audio into text. Using the text result, an AI model is needed to detect the main topic and subtopics along with which parts of the text counts as a “truth statement”.






Modality and Task

Models: Audio / Text (LLM)

This problem requires an audio to text model so the user can input a simple media file, and the text can be transcribed automatically. The LLM is required to process the text output and synthesize valid topics and truth statements for the media provided.


System Architecture

Input file: .mp3, .wav, .mp4 →

Preprocessing: convert to .mp3, noise reduction, normalization, voice activity detection →

Representation: Spectrograms, mel-filterbanks, feature normalization →

Model Inference: Acoustic model (encoder) →
		      Language model (encoder →
		      Decoder (beam search) →

Postprocessing: text normalization / processing, punctuation, timestamps →

Constraints / Policies: File size, tokens →

Output: json including text and timestamps →

Preprocessing: text cleaning, prompt construction →

Representation: Tokenization, positional embeddings →

Model Inference: LLM, Chain-of-Thought model →

Postprocessing: structured parsing (JSON), deduplication of topics / statements, timestamps →

Constraints / Policies: tokens, prompt size →

Output: Structured topic / sub-topics, truth statement list


Initial Model Selection

Model Name: distil-whisper/distil-large-v3

Size: ~756M

Why: This model is very fast compare to larger models and maintains a 99% accuracy 
for transcribing english. It can also format text with punctuation and capitalization which will be vital for the next phase of the process.

Size justification: This model performs very well with its size. Smaller models lack accuracy and most struggle with punctuation. Larger models are slower and the potential gain is very small considering the size and accuracy of this model.


Architectural Constraints

Input files must be below a specific threshold to prevent memory errors and context overflow. 

There must be enough compute available to run the models continuously for two or three hours at a time.

The service must run on the cloud to allow access to files from anywhere.


Expected Failure Modes

The input file size could be too big. This could be a model failure or an architectural failure. The architecture should be able to detect if the file is too big. However, the model might fail because the file is too big to process. To fix this, the architecture should be changed to allow only specific file sizes to be processed.

The transcription could be incorrect or deformed. This would be a failure on the model not being able to detect the correct transcription. To fix this, the architecture could include an accuracy threshold of different parts of the transcription and present a warning if anything falls below the threshold.


Semester Roadmap

During optimization weeks, I will be checking the accuracy and speed of each part of the system, and experimenting with potential preprocessing steps that could increase performance.

During deployment weeks, I will be making sure the user interface is working properly and shows status updates to the user.

For the transcription part of the project, I will measure the speed and accuracy of the transcription. I will also stress test the system with files that are really hard to transcribe, or are just in another language.

For the text processing part o the project, I will measure the percentage of truth statements extracted from the text. I will also be check the accuracy of the topics selected.
