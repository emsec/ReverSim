/**
 * 
 */
class LogData
{
	static index = 0

	/**
	 * Send an event to the server to be logged. The timestamp is added by this function, @see Rq.now()
	 * @param {string} eventDict The event data 
	 */
	static sendData(eventDict, eventPath = 'None:None')
	{
		throw "sendData() is deprecated. Use the new JsonRPC.send() system!";

		/*if(!gamerules.enableLogging)
			return "Logging is disabled"

		// send log information as post
		var data = {
			'logEntry': eventDict,
			'pseudonym': pseudonym,
			'timeStamp': Rq.now(),
			'index': LogData.index++,
			'epath': eventPath
		};
		Rq.post('/addLogEntry', () => {}, data);*/
	}

	/**
	 * Take a screenshot of the current canvas (this will not include any HTML overlays) and send it to the server.
	 * @param {Phaser.Scene} scene 
	 */
	static sendCanvasPNG(scene)
	{
		const IMAGE_FORMAT = 'image/png';
		const IMAGE_QUALITY = 0.8; // Only relevant for jpeg

		if(!gamerules.enableLogging)
			return "Logging is disabled"

		// get canvas as image
		scene.renderer.snapshot((snapshot) => {
			if(!(snapshot instanceof HTMLImageElement))
			{
				console.error('snapshot was not of type HTMLImageElement');
				return;
			}
			
			let data = {
				canvasImage: snapshot.src,
				'pseudonym': pseudonym,
				'timeStamp': Rq.now()
			};

			Rq.post('/canvasImage', () => {}, data, "application/x-www-form-urlencoded; charset=UTF-8");
		}, IMAGE_FORMAT, IMAGE_QUALITY);
	}
}
