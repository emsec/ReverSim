/**
 * BaseScene showing the Information bar at the bottom. 
 * Every scene shall extend this one instead of the regular Phaser.Scene
 */
class BaseScene extends Phaser.Scene
{
	/**
	 * Create a new BaseScene.
	 * @param {string} phase The current phase. This will determine the scene name.
	 */
	constructor(phase)
	{
		super(phase);
		this.phase = phase;
		this.eventList = [];
		this.clickEventList = {};
		this.firstShow = true;

		/** 
		 * This factor controls the margin around circuit elements. By default it is 0, 
		 * set this to 1 to enabled the margin.
		 */
		this.marginFac = 0;

		this.slidesShown = {
			'timerWarning': false
		}

		/** All `setTimeout()` and `setInterval()` timer handles */
		this.timerHandle = {};
		this.timerDuration = null;
		this.timerEnd = null;
	}

	/**
	 * Called by Phaser every time this scene is requested. Sends the current phase to the server.
	 * 
	 * Init step 1
	 */
	create(setting)
	{
		this.serverState = setting;

		// Reset firstShow to true (relevant in case of quali failed)
		this.firstShow = true;

		// set up pointer recognition
		this.input.setTopOnly(true);

		// create a bottom bar / footer
		this.informationBar = new InformationBar(this);

		// Register event handlers
		let e = this.input.on('pointerdown', (pointer, gameObjects, domEvent) => {
			if(!pointer.primaryDown) return;
			this.onPointerDown(pointer, pointer.x, pointer.y, gameObjects);
		}, this);
		this.eventList.push(e);

		e = this.input.on('pointerup', (pointer, gameObjects, domEvent) => {
			if(!pointer.leftButtonReleased()) return;
			this.onPointerUp(pointer, pointer.x, pointer.y, gameObjects);
		}, this);
		this.eventList.push(e);

		// Register dialogue close
		this.registerClickListener("closeDialogue", this.onCloseDialogue);

		// Create ui etc of the child class
		this.createElements(setting);
		
		// Load the first level/info/whatever
		// Make sure to call `this.show()` after you are done setting your stuff up
		this.loadNext(setting);
	}

	/**
	 * Called by Phaser3 if the player presses down the left mouse button
	 * @param {Phaser.Input.Pointer} pointer 
	 * @param {number} localX x-Position of cursor in screen space coordinates
	 * @param {number} localY y-Position of cursor in screen space coordinates
	 * @param {Phaser.GameObjects.GameObject[]} gameObjects 
	 * @returns 
	 */
	onPointerDown(pointer, localX, localY, gameObjects)
	{
		let clickedObjectList = this.input.hitTestPointer(pointer);
		this.input.sortGameObjects(clickedObjectList, pointer);
		this.clickedObject = clickedObjectList[0];
	}

	/**
	 * Called by Phaser3 after the user released the left mouse button
	 * @param {Phaser.Input.Pointer} pointer 
	 * @param {*} localX x-Position of cursor in screen space coordinates
	 * @param {*} localY y-Position of cursor in screen space coordinates
	 * @param {Phaser.GameObjects.GameObject[]} gameObjects 
	 */
	onPointerUp(pointer, localX, localY, gameObjects)
	{
		// Make sure the mouse button was released over an object
		let clickedObjectList = this.input.hitTestPointer(pointer);
		this.input.sortGameObjects(clickedObjectList, pointer);
		let gameObject = clickedObjectList[0];
		
		if(gameObject == null) return;

		// Make sure the mouse button was pressed and released over the same object
		if(gameObject != this.clickedObject)
			return;

		// Get the name/identifier of the event and make sure that a method is registered for this ident
		var type = gameObject.getData('type');
		if(this.clickEventList[type] === undefined) return;

		// Call the method that is registered under that identifier
		this.clickEventList[type].call(this, gameObject);

		// Flush the JsonRPC action que and send them all to the server
		JsonRPC.flush();

		this.clickedObject = null;
	}

	/**
	 * Get the current phase. The gamePhase is set once in the constructor and shall never be changed.
	 * @returns {string} The current phase. Currently there is no lookup performed, the output is the same as 
	 * 					 this.phase, but this might change.
	 */
	getPhase()
	{
		return this.phase;
	}

	/**
	 * Called by Phaser once per game step while the scene is running.
	 */
	update() { }

	/**
	 * Init the gui and states for this scene.
	 * Called after the phase has been send to the server. 
	 * 
	 * Use this method to initialize your gui elements when overriding the BaseScene class
	 * 
	 * Init step 2
	 */
	createElements(setting) 
	{ 
		// new scene starts with new camera, so enforce that we're in black screen
		// (the previous scene will have faded to black) before setting up our UI,
		// which would otherwise cause flashing
		AniLib.blackScreen(this);
	}

	/**
	 * @param {string} name
	 * @param {{(gameObject: any): void;}} func
	 */
	registerClickListener(name, func)
	{
		this.clickEventList[name] = func;
	}

	/**
	 * Remove the event listener with that given name.
	 * @param {string} name The unique identifier/name of the event to remove.
	 */
	removeClickListener(name)
	{
		delete this.clickEventList[name];
	}

	/**
	 * Called before unloading the scene, while the client is requesting the next scene. 
	 * This should prevent double next events from happening
	 */
	beforeSuspendUI() {
		
	}

	/**
	 * Request the next phase/level or whatever follows next, the server will decide.
	 * 
	 * Call this to continue to whatever is next (e.g. after a level was solved)
	 */
	next()
	{
		// this is mostly used to let BaseScene disable its (potentially)
		// running timer because we can't have a timer expire after we've
		// already called /status?action=next (this breaks the session state)
		this.beforeSuspendUI();

		JsonRPC.que("next", {});
		JsonRPC.send("status", {}, (data, success) => {
			if(!success)
				console.error(data);

			// fully fade to black, then switch levels/phases
			AniLib.darkenScreen(this, () => {
				let phase = data.phase;

				if(phase == this.phase)
					this.loadNext(data);
				else
					this.nextPhase(phase, data);
			});
		});
	}

	/**
	 * Start whatever is next. In case of the GameScene this is for e.g. a level or info.
	 * 
	 * When called for the first time the ui finished loading and it is now time to load some level specific
	 * stuff. This method can also be called multiple times if there is more than one level/info whatever.
	 * 
	 * The screen is guaranteed to be transitioned to black at this point.
	 * 
	 * Fade from black into the current level or whatever by calling `this.show(fileType)`
	 * The base method will call show() on its own, if not overridden!
	 * @param {*} data 
	 */
	loadNext(data) 
	{ 
		this.serverState = data;
		this.show(); 
	}

	/**
	 * Fade from black into whatever was loaded behind the curtain (level, info, etc.).
	 */
	show()
	{	
		// The countdown for Phases with Levels will be started later after the 
		// first level was loaded. This way the countdown does not start for 
		// info screens etc.
		if(this.hasTimeLimit() && !(this instanceof GameScene))
			this.startCountdown();

		AniLib.showScreen(this);
		if(this.firstShow)
		{
			JsonRPC.send("chrono", ["phase", this.phase, "start", Rq.now()]);
			this.firstShow = false;
		}
	}

	/**
	 * Switch to the next scene/phase. Called after the server announced a different scene than before.
	 * @param {string} phase
	 * @param {object} setting
	 */
	nextPhase(phase, setting)
	{
		this.cleanUp();

		if(phase == 'End of game' || phase == 'finished')
		{
			// If the server is correctly configured, this will never be executed. But showing the end screen 
			// just to be sure
			this.scene.start('FinalScene');
		}
		else
		{
			console.log('Changing scene to "' + phase + '"');
			this.scene.start(phase, setting);
			currentScene = phase;
		}
	}

	/**
	 * Add a bigger smaller animation to the button
	 * @param {RectButton} button 
	 */
	highlightButton(button, targetSize = 1.1, duration = 1500)
	{
		AniLib.scaleUpDownAnimation(button.getObjects(), targetSize, targetSize, duration, this);
	}

	/**
	 * Check if a time limit is configured for this phase
	 * @returns True if this phase has a time limit, false otherwise.
	 */
	hasTimeLimit() 
	{ 
		if('timerPhaseDuration' in this.serverState && this.serverState['timerPhaseDuration'] > 0)
			return true;

		if('timerGlobalDuration' in this.serverState && this.serverState['timerGlobalDuration'] > 0)
			return true;

		return false;
	}

	/**
	 * If this phase has a time limit, start/update the countdown. 
	 * 
	 * Multiple calls to this method won't do any damage, they will just update the countdown time.
	 */
	startCountdown()
	{
		// Make sure no countdown is running
		this.stopCountdown();

		const names = ['timerPhase', 'timerGlobal'];

		const baseLine = Rq.now();

		// The durations advertised by the server
		let advTimerStart, advTimerDuration, advTimerName = null;

		// Get the timer that will end first
		for(let n of names)
		{
			if(!(n + 'Duration' in this.serverState)) continue;

			const startVal = this.serverState[n + 'Start']
			const durVal = this.serverState[n + 'Duration']
			
			// Make sure `timerStart` and `timerDuration` are initialized
			if(advTimerStart == null || advTimerDuration == null)
			{
				advTimerStart = startVal;
				advTimerDuration = durVal;
				advTimerName = n;
			}

			// If the timer has not started yet (chrono event not fired, therefore server sends -1)
			// take the current time as the baseline as the timer will be started now.	
			let simStart = (x) => x > 0 ? advTimerStart : baseLine; 		
			if(simStart(advTimerStart) + advTimerDuration > simStart(startVal) + durVal)
			{
				// If the timer will end earlier, make it the current timer
				advTimerStart = startVal;
				advTimerDuration = durVal;
				advTimerName = n;
			}
		}

		// Reduce duration if the timer was started before, otherwise start the timer as advertised by the server
		this.timerDuration = advTimerStart > 0 ? advTimerStart + advTimerDuration - Rq.now() : advTimerDuration;

		if(this.timerDuration < 1)
		{
			// Could not start the timer because it is already over
			this.onTimerEnd(); // TODO A race condition might trigger this method twice even with this check
			console.log("Timer expired before level load completed, not initializing level");
			AniLib.showScreen(this);
		}
		else
		{
			// Start the new timers (setTimeout takes milliseconds as argument)
			let timerStart = Rq.now();
			this.timerHandle.reminder = setTimeout(this.onAlertTimer.bind(this), this.timerDuration - gamerules["reminderTime"]*1000);
			this.timerHandle.end = setTimeout(this.onTimerEnd.bind(this), this.timerDuration);
			this.timerEnd = Math.max(0, timerStart + this.timerDuration);
		}

		// Que the countdown message, it will be send later by show()
		JsonRPC.que("chrono", ["countdown", this.phase, "start", Rq.now(), this.timerDuration/1000]);
		console.log("Time: " + this.timerDuration/1000 + " seconds remaining until " + advTimerName + ".");
	}

	stopCountdown()
	{
		clearTimeout(this.timerHandle.reminder);
		clearTimeout(this.timerHandle.end);
		clearTimeout(this.timerHandle.level);
		clearInterval(this.timerHandle.reminderText);
		this.timerEnd = null;
	}

	/**
	 * Remind the participant, that he/she is running out of time.
	 */
	onAlertTimer()
	{
		const timeRemaining = Math.max(Math.min(
			this.timerEnd != null ? (this.timerEnd - Rq.now())/1000 : gamerules.reminderTime, 
			gamerules.reminderTime
		), 0);

		console.log("Timer: " + timeRemaining + " seconds remaining!");

		// Write to the logfile
		JsonRPC.send("popup", {"content": "timeRemaining", "action": "show", "a": timeRemaining});

		if('timerReminderText' in this)
		{
			let currentTime = Math.floor(timeRemaining);
			let updateText = () => {
				let rawText = LangDict.get('timeRemaining');
				rawText = rawText.replace("%d", String(Math.max(0, currentTime--)));
				
				// @ts-ignore
				this.timerReminderText.setText(rawText);
			};
			updateText(); 
			// @ts-ignore
			this.timerReminderText.setVisible(true);
			this.timerHandle.reminderText = setInterval(updateText.bind(this), 1000);
		}
		else
		{
			if(this.slidesShown.timerWarning)
				return;

			// @ts-ignore
			this.timerReminder = new Alert(this, "timerWarning", "ok", "closeDialogue", 100); // @ts-ignore
			this.timerReminder.replaceText("%d", Math.floor(timeRemaining));
		}

		this.slidesShown.timerWarning = true;
	}

	/**
	 * The timer has ended
	 */
	onTimerEnd()
	{
		// Write to the logfile
		JsonRPC.que("chrono", ["countdown", this.phase, "stop", Rq.now()], () => {
			this.onTimeoutConfirmed()
		});
		JsonRPC.send("popup", {"content": "timerEnd", "action": "show"});

		// Show the timer end dialogue
		console.log("Timer: End!");
		this.timerEndDialog = new Alert(this, "timerEnd", "ok", "closeDialogue", 110);
	}

	/**
	 * Called after the `onTimerEnd()` method was confirmed by the server. Can be used to prevent double next clicks.
	 */
	onTimeoutConfirmed() {}

	/**
	 * Close both the timerReminder and the timerEndDialog.
	 * @param {*} gameObject 
	 */
	onCloseDialogue(gameObject)
	{
		if(this.timerReminder && this.timerReminder.isVisible())
		{
			this.timerReminder.setVisible(false);
			JsonRPC.que("popup", {"content": "timeRemaining", "action": "hide"});
		}

		if(this.timerEndDialog && this.timerEndDialog.isVisible())
		{
			this.timerEndDialog.setVisible(false);
			JsonRPC.que("popup", {"content": "timerEnd", "action": "hide"});
		}
	}

	/**
	 * Some Scenes will have a smaller canvas for the elements (logic gates, wires, etc.). The layouter will always 
	 * calculate the positions in screen space coordinates, however they might need to be transformed to visually fit 
	 * on screen without overlapping, therefore we introduce the level coordinate system.
	 * @param {number} x The x coord in screen space coordinates.
	 * @param {number} y The y coord in screen space coordinates.
	 */
	levelToScreenCoords(x, y)
	{
		return BaseScene.levelToScreenCoords(x, y, this.marginFac);
	}

	/**
	 * Remove all event listeners and clean up every GameObject. 
	 * When overriding this method make sure to also call the super method!
	 */
	cleanUp() 
	{
		// First make sure no countdown fires during cleanup
		this.stopCountdown();

		// Remove all Click Listeners
		for(const e of this.eventList)
			this.input.removeListener(e);

		this.input.removeAllListeners();

		this.beforeSuspendUI();
	}

	/**
	 * Get a string path of the current location of the player (current Phase, Level etc.)
	 * @returns e.g. Scene or Scene/Level
	 */
	getLocation()
	{
		return this.getPhase();
	}

	/**
	 * Calculate the screen coordinates from the given level coordinates.
	 * Useful since some scenes might have a margin around the level.
	 * @param {number} xPos X-coordinate in level space.
	 * @param {number} yPos Y-coordinate in level space.
	 * @param {number} marginFac 1 if you want to add a margin, 0 otherwise.
	 * @returns The x and y coordinates in screen space.
	 */
	static levelToScreenCoords(xPos, yPos, marginFac = 1)
	{
		const canvasWidth = config.width;
		const canvasHeight = config.height;
		const lm = this.levelMargins;

		return {
			'x': LineDrawer.map(xPos, 0, canvasWidth, lm.left * marginFac, canvasWidth - lm.right * marginFac), 
			'y': LineDrawer.map(yPos, 0, canvasHeight, lm.top * marginFac, canvasHeight - lm.bottom * marginFac)
		};
	}

	/**
	 * Calculate the level coordinates from the given screen coordinates.
	 * Useful since some scenes might have a margin around the level.
	 * @param {number} x X-coordinate in screen space.
	 * @param {number} y Y-coordinate in screen space.
	 * @param {number} marginFac 1 if you want to add a margin, 0 otherwise.
	 * @returns The x and y coordinates in level space.
	 */
	static screenToLevelCoords(x, y, marginFac = 1)
	{
		const canvasWidth = config.width;
		const canvasHeight = config.height;
		const lm = this.levelMargins;

		return {
			'xPos': LineDrawer.map(x, lm.left * marginFac, canvasWidth - lm.right * marginFac, 0, canvasWidth), 
			'yPos': LineDrawer.map(y, lm.top * marginFac, canvasHeight - lm.bottom * marginFac, 0, canvasHeight)
		};
	}
}

BaseScene.levelMargins = {
	"left": 70,
	"right": 0,
	"top": 0,
	"bottom": 25
}

var currentScene;