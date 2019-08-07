# A Wrapper App for Automated Measurements with YouTube’s Native Mobile App (YoMo Wrapper App)
## Monitoring of the Native Android YouTube App
A measurement application to measure the native YouTube mobile app in Google Play Store for Android smartphones. Among other things, the current quality and playing time is read from the app and written in a log file.

### QoE Monitoring of the Native Android YouTube App
**Goal of the app**
   - Implementation of a measurement concept on monitoring of application-layer key performance indicators of YouTube
   - Key performance indicators are chosen that have a high correlation with actual QoE of mobile users
   
**Basic functionalities**
   - Measurement of the native Google YouTube app
   - Monitoring of playback behavior of YouTube video streams
   - Automatic measuring procedure with adjustment of playback quality and measurement of different videos
   - Traffic measurement and setting of network conditions
   
**App description**
   - Android app based on Android Testing Support Library
   - Starts the native YouTube app within the wrapper app
   - uiautomator to detect window elements and streaming events such as playback progress, reading of stats-for-nerds

### More information
   - [Documentation](https://raw.githubusercontent.com/lsinfo3/yomo-wrapperapp/master/Documentation.pdf)
   - [Slides @Speakerdeck](https://speakerdeck.com/userflo/a-public-dataset-for-youtubes-mobile-streaming-client)

### Publications
* Dataset: [QoE³ - A public dataset for YouTube's Mobile Streaming Client](http://qoecube.informatik.uni-wuerzburg.de/)
* [Demo @ IEEE/IFIP NOMS 2018: QoE Monitoring of the Native Android YouTube App](https://www.bibsonomy.org/bibtex/28c37b15dc76f4351ea60e98e76bdacbc/uniwue_info3)
* [Poster (PDF)](https://www.dropbox.com/s/sfvj3y5jmj8f4ks/DemoWrapperApp%20v1.0.pdf?dl=1)


University of Würzburg - Webpage: https://go.uniwue.de/videoqoe

[Contact](http://www.comnet.informatik.uni-wuerzburg.de/en/staff/members/florian-wamser/)
