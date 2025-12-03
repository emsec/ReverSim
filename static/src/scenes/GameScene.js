/**
 * Base class for different scenes like the qualification and competition scene.
 */
class GameScene extends BaseScene
{
	/**
	 * Create a new GameScene. This object shall be instanciated for every phase change.
	 * 
	 * The difficulty is controlled by the phase name and can be configured inside `phaseDifficulty`. 
	 * If no difficulty is configured for this phase, the game will default to EASY.
	 * @param {string} phase Name of the phase, for e.g. quali or competition
	 */
	constructor(phase, activateDrawing = true)
	{
		super(phase);
		this.activateDrawing = activateDrawing;
		this.taskNmbr = 0;
		this.numTasks = 0;
		this.localTaskCounter = 0;
		this.showState = false;
		this.solved = false; // True if a correct solution was confirmed
		this.timeLimit = -4;

		// Set Gamemode, falling back to EASY if phase is not found in phaseDifficulty table.
		this.gameMode = phaseDifficulty[phase] ? phaseDifficulty[phase] : DIFFICULTY.MEDIUM;

		Object.assign(this.slidesShown, {
			'introCamouflage': false,
			'introCovert': false,
			'introConfirm': false,
			'levelTimeLimit': false
		});

		this.slidePaths = {
			"level": "/assets/levels/differentComplexityLevels",
			"info": "/assets/levels/infoPanel",
			"special": "/assets/levels/special"
		}
		
		/** Enable level margins by setting the margin factor to 1. Will be disabled for info slides etc. */
		this.marginFac = 1;
	}

	/**
	 * Init the gui and states for this scene.
	 * Called after the phase has been send to the server. 
	 * 
	 * Init step 2
	 */
	createElements(setting)
	{
		super.createElements(setting);

		// create CanvasDrawing object to be able to draw
		this.draw = new CanvasDrawing(this);
		this.draw.create();
		this.draw.logDrawingActions();
		this.draw.setVisible(false);

		if(this.activateDrawing)
			this.draw.activateDrawing();
		else
			this.draw.deactivateDrawing();

		this.feedbackPopUp = new Alert(this, 'feedbackClicks', 'onWeGo', 'PopUp_Alert_Feedback');
		this.feedbackPopUp.txt.setStyle({ align: 'center' });
		this.feedbackPopUp.setVisible(false);

		// let's cheat a bit -> skip to next level without solving the current level
		//let e = this.input.keyboard.on('keydown-' + 'W', () => this.loadNextLevel());
		//this.eventList.push(e); // Add event listener to list, this will be needed to clean them up when the scene is done

		// Register the event handlers for every button / switch click
		this.registerClickListener('Switch', this.onSwitchClicked);
		this.registerClickListener('Okay', this.onNextLevelButtonClicked);
		this.registerClickListener('ConfirmButton', this.onConfirmButtonClicked);
		this.registerClickListener('Continue', this.onInfoPanelConfirmed);
		this.registerClickListener('PopUp_Alert_Feedback', this.onCloseFeedbackAlert);
		this.registerClickListener('SimulateLevelButton', this.onSimulateButtonClicked);
		
		// Complete the rest of the init steps
		this.initScore();
		this.initButtons();
		this.initChildren();

		// Enable console cheat
		cheat.skip = this.next.bind(this);

		// Make sure level counter is zero when returning from ElementIntro
		this.taskNmbr = 0;
		this.numTasks = 0;
		this.localTaskCounter = 0;
		this.levelName = "NONE";
		this.levelType = "NONE";
	}

	initScore()
	{
		this.levelOverlay = new LevelStatusOverlay(this);
		this.timerReminderText = AddText.addTextFromLib(this, config.width - 50, 600, 'timeRemaining');
		this.timerReminderText.setOrigin(1, 0);
		this.timerReminderText.setVisible(false);
	}

	/**
	 * Init step 4
	 */
	initButtons()
	{
		// create nextLevelButton and make it interactive
		this.nextLevelButton = new RectButton(this, 0, 0, 'nextLevel', 'right', 'Okay');

		// create confirm button
		this.confirmButton = new RectButton(this, 0, 0, 'confirm', 'right', 'ConfirmButton');
		this.confirmButton.disableInteractive();

		// create button to simulate/probe the level, the position gets updated by the button bar in loadNextLevel()!
		this.simulateLevelButton = new RectButton(this, 0, 0, 'startSimulatingLevel', 'right', 'SimulateLevelButton');

		this.buttonBar = new ButtonBar(this, [
			this.nextLevelButton, this.confirmButton, this.simulateLevelButton
		], config.width - 20, config.height*0.88);

		this.buttonBar.setButtonVisible(this.nextLevelButton, false, false);
		this.buttonBar.setButtonVisible(this.simulateLevelButton, false);
	}

	/** 
	 * Init step 5 
	 * Use this method to initialize your stuff when you extend this class
	 */
	initChildren() { }

	// @Override
	loadNext(serverState)
	{
		this.levelName = serverState.levelName;
		this.levelType = serverState.levelType;
		this.serverState = serverState;
		
		// Get the number of tasks from the server
		if("numTasks" in serverState && "taskIdx" in serverState)
		{
			this.numTasks = serverState["numTasks"];
			this.taskNmbr = serverState["taskIdx"];
			GameScene.levelsToGo = this.numTasks;
		}

		console.log('Loading ' + this.levelType + ' "' + this.levelName + '"');

		// If the level/info slide is not hardcoded, request it from the server (tutorial is hardcoded)
		if(this.levelType in this.slidePaths)
		{
			Rq.get(this.slidePaths[this.levelType] + '/' + this.levelName, (levelString) => {
				this.startNext(this.levelType, levelString);
			});
		}
		else
			this.startNext(this.levelType, this.levelName);
	}

	/**
	 * Start loading either the response from the server or the local tutorial
	 * @param {string} fileType
	 * @param {string} response 
	 */
	startNext(fileType, response)
	{
		// Clean the ui from last level/info/tutorial
		this.cleanLast();
		
		// Call the load method that matches the fileType
		switch (fileType) {
			case "level":		this.loadLevel(response); break;
			case "info":		this.loadInfo(response); break;
			case "tutorial":	this.loadTutorial(response); break;
			case "localLevel": 	this.loadLevel(response); break;
			case "special": 	this.loadSpecial(response); break;
			default:			this.loadWhatever(fileType, response); break;
		}

		// Fade from black into the current level/info/etc
		this.show();

		// Send level shown event
		// Param 2 type is level/info/etc
		const timeLimit = this.level == null ? null : this.level.getTimeLimit();
		JsonRPC.send("chrono", [this.levelType, this.getLocation(), "start", Rq.now(), timeLimit]);
	}

	/**
	 * Clean the stuff from the last level etc.
	 */
	cleanLast()
	{
		if(this.level && this.level.circuit != null) this.level.circuit.cleanUp();
		this.level = null;
		if(this["infoPanel"]) this.infoPanel.cleanUp();
		
		this.timerReminderText.setVisible(false);
		this.buttonBar.updatePositions();
		this.draw.clearRenderTexture();

		// Clear level cheats
		cheat.solve = _cheatNotLoaded
	}

	/**
	 * Update the ui for the next info/tutorial
	 * @param {string} type
	 */
	prepareInfoTut(type)
	{
		this.marginFac = 0;

		// hide confirm button
		this.buttonBar.setButtonVisible(this.confirmButton, false);
		this.buttonBar.setButtonVisible(this.nextLevelButton, false);

		// do not show drawing tools and what was painted
		this.draw.setVisible(false);

		// Update the level overlay
		if(this.levelOverlay != null)
			this.levelOverlay.infoTutLoaded();
	}

	/**
	 * Update the ui for the next level
	 * @param {Level} level
	 */
	prepareLevel(level)
	{
		this.marginFac = 1;
		this.solved = false;

		// Show Drawing tools
		this.draw.setVisible(this.activateDrawing);
		this.setDrawingEnabled(this.activateDrawing);
		this.draw.clearRenderTexture();

		// make the switches interactive
		this.registerClickListener('Switch', this.onSwitchClicked);

		// If this is the last level, adjust the nextLevelButton to show a different text
		if(this.taskNmbr >= this.numTasks)
			this.buttonBar.setButtonText(this.nextLevelButton, LangDict.get('next'), false);

		// make confirmButton visible and interactive
		this.buttonBar.setButtonVisible(this.confirmButton, true, false);
		this.confirmButton.setInteractive();

		// Hide the next level button and remove the animation
		this.buttonBar.setButtonVisible(this.nextLevelButton, false, false);
		AniLib.clearAnimations(this.nextLevelButton.getObjects(), this);
		AniLib.clearAnimations(this.confirmButton.getObjects(), this);
		this.nextLevelButton.setInteractive();

		// Update the level overlay
		this.levelOverlay.levelLoaded(level, this.taskNmbr, this.numTasks);
		this.buttonBar.updatePositions();
	}

	loadInfo(response)
	{
		this.prepareInfoTut("info");

		// create info Panel
		this.infoPanel = new InfoPanel(this, response);
	}

	loadTutorial(response)
	{
		this.prepareInfoTut("tutorial");

		switch(response)
		{
			case 'camouflage': 	this.infoPanel = new IntroduceCamouflageOptionOne(this); break;
			case 'covert': 		this.infoPanel = new IntroduceCamouflageOptionThree(this); break;
			default: 			console.error('Unknown tutorial: ' + response); break;
		}
	}

	loadSpecial(response)
	{
		this.prepareInfoTut("special")

		// The path contains the information, which type of special to load e.g. "retut/voluntaryTutorial.txt"
		const specialType = this.levelName.split('/', 1)[0];

		switch(specialType)
		{
			case 'retut': 
				this.infoPanel = new VoluntaryTutorial(this, response); break;

			case 'pause': 
				this.infoPanel = new PausePanel(this, response, gamerules.pause.duration, this.serverState.levelStart); 
				break;

			default: 
				console.error(`Unknown special slide: "${this.levelName}". See doc/LevelList.md`); 
				break;
		}
	}

	/**
	 * Load a file type which is not known to GameScene. Override this in any child classes.
	 * The screen will fade into the next level after this method returns (see `GameScene.loadNext()`).
	 * @param {*} fileType 
	 * @param {*} levelName 
	 */
	loadWhatever(fileType, levelName)
	{
		console.error("Unexpected type for level, got " + fileType);
	}

	/**
	 * Display the given level. Called by handleResponse()
	 * @param {string} levelStr The raw level file string. The encoding of the level files is configured inside game.js `config.LEVEL_ENCODING`
	 */
	loadLevel(levelStr)
	{
		this.marginFac = 1; // Note: The margin factor has to be set before Level() is called
		this.localTaskCounter++;
		this.level = new Level(levelStr, this.getDifficulty(), this.getPhase(), this);
		this.solved = false;

		// Enable Cheats
		cheat.solve = this.level.circuit.calculateAllSolutions.bind(this.level.circuit, false, this.level.initialSwitchStates);

		// Show the simulate Level button on medium difficulty
		if(this.gameMode == DIFFICULTY.MEDIUM && mediumShowSimulateButton)
			this.buttonBar.setButtonVisible(this.simulateLevelButton, true);

		// Update ui to show level
		this.prepareLevel(this.level);

		// Apply the data from the server if the level was started before
		this.applyServerState(this.serverState);

		// Calculate the level logic state and display it to the user depending on the difficulty
		this.updateLevelState(false);

		// Start the countdown if this phase has a time limit
		if(this.hasTimeLimit())
			this.startCountdown();

		// Start the level countdown if configured
		this.startLevelTimeLimit(this.level.getTimeLimit());
	}

	/**
	 * 
	 * @param {number} timeLimit Number of seconds configured in the level file
	 */
	startLevelTimeLimit(timeLimit)
	{
		// Don't start the countdown for levels with disabled (or too small) time limit
		if(timeLimit < 0.5)
			return;

		// Subtract the passed time if level was already started
		if('levelStart' in this.serverState && this.serverState.levelStart > 1000)
			timeLimit = timeLimit - (Rq.now() - this.serverState.levelStart)/1000;

		console.log("Time in seconds to solve this level: " + timeLimit + ".");

		if(timeLimit < 0.5)
			this.onLevelTimerEnd();
		else
			this.timerHandle.level = setTimeout(this.onLevelTimerEnd.bind(this), timeLimit * 1000);
	}

	// @Override
	beforeSuspendUI()
	{
		super.beforeSuspendUI();
		this.stopCountdown();
		
		AniLib.clearAnimations(this.simulateLevelButton.getObjects(), this);
		AniLib.clearAnimations(this.nextLevelButton.getObjects(), this);

		// Hide the end simulation button
		this.buttonBar.setButtonVisible(this.simulateLevelButton, false);
		this.showState = false;

		// End the simulation cooldown (if existing)
		this.tweens.getTweens().forEach(function(tween) {
			tween.pause();
			tween.complete();
		});
	}

	/**
	 * Enable or disable the drawing feature.
	 * @param {boolean} activateDrawing True if the user shall be able to draw on the canvas, false otherwise.
	 */
	setDrawingEnabled(activateDrawing)
	{
		this.activateDrawing = activateDrawing;

		if(activateDrawing)
			this.draw.activateDrawing();
		else
			this.draw.deactivateDrawing();
	}

	/**
	 * Get the current difficulty. 
	 * @returns {string} Either EASY (power is always visible), MEDIUM (power is only shown when probing), ADVANCED   or HARD (power is never shown).
	 */
	getDifficulty()
	{
		return phaseDifficulty[this.getPhase()];
	}

	/**
	 * Update the level score and display/update the (changed) value
	 * @param {string} operationName The identifier of the action
	 * @see scoreValues in Level.js
	 */
	updateScore(operationName)
	{
		this.level.updateScore(operationName);
		this.levelOverlay.updateScore(this.level.stats.score)
	}

	/**
	 * Return if the level is solved successfully (all switches are in the correct position).
	 * @returns True if the level solution is correct, false otherwise.
	 */
	getSolvingState()
	{
		return Boolean(this.level.getSolvingState());
	}

	applyServerState(serverState)
	{
		// No server state was send
		if(!("switches" in serverState || "switchOverride" in serverState))
			return;

		this.solved = serverState.solved;
		let switchElements = this.level.circuit.elementsManager.getSwitches();

		// if level has server-side initialization overrides
		if("switchOverride" in serverState) {
			// server-defined state takes precedence over defaults from level file
			for(let [id, val] of Object.entries(serverState.switchOverride))
				switchElements.find((x) => x.id == id).switchClicked(val);
			this.level.resetInitialSwitchStates();
		}
		
		// if level is dirty
		if("switches" in serverState) {
			// Update level stats UI
			this.level.stats.switchClickCtr = serverState.switchClicks;
			this.level.stats.confirmClickCtr = serverState.confirmClicks;

			// NOTE: Simulate Clicks are not stored server side, use confirm clicks instead
			if([DIFFICULTY.MEDIUM, DIFFICULTY.ADVANCED].includes(this.getDifficulty()))
				this.level.stats.simulateCtr = serverState.confirmClicks;

			this.levelOverlay.updateSwitchClicks(serverState.switchClicks);
			this.levelOverlay.updateConfirmClicks(serverState.confirmClicks);

			// change switch states to user's saved inputs
			for(let [id, val] of Object.entries(serverState.switches))
				switchElements.find((x) => x.id == id).switchClicked(val);

			// Freeze inputs if level was solved and show next level button
			if(serverState.solved)
			{
				this.draw.deactivateDrawing();
				this.level.setSwitchesInteractive(false);

				// Show and animate the next button
				this.showNextButton(true);
				this.highlightButton(this.nextLevelButton);
			}
		}
	}

	/**
	 * Update the internal state of the level and depending on the difficulty display the state to the player.
	 * @param {boolean} confirmClick True if the triggering event is a confirm click.
	 */
	updateLevelState(confirmClick)
	{
		const switchStateCorrect = this.getSolvingState();
		let state = {
			wireStateVisible: false,
			outputStateVisible: false
		};

		// On easy the state is always shown
		if(this.gameMode == DIFFICULTY.EASY)
		{
			state.wireStateVisible = true;
			state.outputStateVisible = true;
			this.solved = switchStateCorrect;
		
			// show hook aka next level button if level is solved
			if(switchStateCorrect)
				this.showNextButton(true);
		}

		// On all other difficulties the state can only be shown after a confirm click/simulation.
		// When the level is confirmed as solved also show the state.
		else if(confirmClick || this.solved)
		{
			// Level states on MEDIUM are shown when simulating/solved
			if(this.gameMode == DIFFICULTY.MEDIUM)
			{
				state.wireStateVisible = true;
				state.outputStateVisible = true;
			}
			// Wire states on ADVANCED are only shown when solved, output states are shown when simulating/solved
			else if(this.gameMode == DIFFICULTY.ADVANCED)
			{
				state.wireStateVisible = switchStateCorrect;
				state.outputStateVisible = true;
			}
			// Level states on HARD are only shown, if level is solved
			else if(this.gameMode == DIFFICULTY.HARD)
			{
				state.wireStateVisible = switchStateCorrect;
				state.outputStateVisible = switchStateCorrect;
			}
		}
		
		// Update the level ui
		this.level.circuit.setShowState(state.wireStateVisible, state.outputStateVisible);
		this.level.calculateOutputs();
		this.level.circuit.wireDrawer.drawWires();
	}

	/**
	 * Called whenever a player is clicking a switch in the circuit.
	 * @param {Phaser.GameObjects.GameObject} gameObject The switch that was clicked
	 */
	onSwitchClicked(gameObject)
	{
		// if level is already solved, do not count switch clicks
		if(!this.solved)
			this.levelOverlay.updateSwitchClicks(++this.level.stats.switchClickCtr);

		// change switch state
		gameObject.getData('element').switchClicked();

		// Calculate outputs and depending on the difficulty visualize level state
		this.updateLevelState(false);

		// Get the new level state and send it together with the switch click
		let levelState = this.level.circuit.getElementStatesJson();
		levelState["id"] = gameObject.getData("id");
		levelState["solved"] = this.getSolvingState() ? 1 : 0;
		JsonRPC.send("switch", levelState);

		// send screenshot
		LogData.sendCanvasPNG();

		// Update the scoreboard
		this.updateScore('switchClick');
	}

	/**
	 * Called when the player uses the simulate feature on medium difficulty. 
	 * Will be called once the simulation is started and once again when finished. Keeps track of the state internally
	 * @param {boolean} writeLogData True if a message shall be send to the server and the score shall be incremented, false otherwise
	 */
	onSimulateButtonClicked(writeLogData = true)
	{
		this.showState = !this.showState;

		if(this.showState)
		{
			if(writeLogData)
			{
				JsonRPC.que("simulate", {"status": 1, "user": 1})
				this.updateScore('simulate');
				this.level.stats.simulateCtr++;
			}

			// Show simulate button and disable input
			this.buttonBar.setButtonTextLabel(this.simulateLevelButton, 'stopSimulatingLevel', false);
			this.buttonBar.setButtonVisible(this.simulateLevelButton, true, false);
			this.setInputEnabled(false);
			if (!gamerules.simulationAllowAnnotate) {
				this.setDrawingEnabled(false);
			}

			if(writeLogData)
			{
				this.simulateLevelButton.setInteractive();
				this.highlightButton(this.simulateLevelButton);
			}
		}
		else 
		{
			if(writeLogData)
				JsonRPC.que("simulate", {"status": 0, "user": 1})
			AniLib.clearAnimations(this.simulateLevelButton.getObjects(), this); // Animation has to be removed before changing text, otherwise glitches occur
			this.buttonBar.setButtonTextLabel(this.simulateLevelButton, 'startSimulatingLevel', false);
			this.buttonBar.setButtonVisible(this.simulateLevelButton, mediumShowSimulateButton);

			// Reenable inputs
			this.setInputEnabled(true);
			if (!gamerules.simulationAllowAnnotate) {
				this.setDrawingEnabled(true);
			}
		}

		// Update the level and variable
		this.updateLevelState(this.showState);
		this.buttonBar.updatePositions();
	}

	onLevelSolved()
	{
		// Update the score
		this.updateScore('correctSolution');

		// show nextLevelButton and hide confirmButton
		this.confirmButton.disableInteractive();

		// update the level state
		this.updateLevelState(true);

		// Show feedback alert, will call JsonRPC.send()
		this.showFeedbackAlert();

		// Hide the confirm button and display the next level button instead
		this.showNextButton(false); // Will become interactive after the feedback dialogue is closed

		// Disable all switches and the drawing feature
		this.level.setSwitchesInteractive(false);
		this.draw.deactivateDrawing();
	}

	onLevelFailed(enableWrongSolutionCountdown = true)
	{
		// show error Signal
		this.error = new ErrorSignal(this, config.width / 2, config.height / 2);
		this.error.create();
		
		// Show end simulation button
		if([DIFFICULTY.MEDIUM, DIFFICULTY.ADVANCED].includes(this.gameMode))
			this.onSimulateButtonClicked(false);

		// Cooldown before the user can interact with the level again
		if(enableWrongSolutionCountdown)
			this.startWrongSolutionCooldown();

		// Level is not correctly solved, add penalty
		this.updateScore('wrongSolution');
	}

	/**
	 * Called when the player presses confirm
	 * gameObject may be null when called by something other than the click listener
	 */
	onConfirmButtonClicked(gameObject)
	{
		// refresh number of clicks
		this.levelOverlay.updateConfirmClicks(++this.level.stats.confirmClickCtr);
		
		let state = this.getSolvingState();

		// log data
		let levelState = this.level.circuit.getElementStatesJson();
		levelState["solved"] = state ? 1 : 0;
		levelState["user"] = gameObject != null ? 1 : 0;

		if(state)
		{
			// Level is solved
			JsonRPC.que("chrono", [this.levelType, this.getLocation(), "stop", Rq.now()]);
			JsonRPC.que("confirm", levelState);
			console.log("Confirm: Level is solved.")

			// show state of wires if level solved (onLevelSolved() will display the feedback dialogue)
			this.onLevelSolved();
		} else
		{
			// Level is not solved
			JsonRPC.que("confirm", levelState);
			console.log("Confirm: Level not solved!")
			this.onLevelFailed(gameObject != null);
		}
		JsonRPC.flush();
		return state;
	}

	onInfoPanelConfirmed(gameObject) {
		// info panels are never reused, so we can just disable its button
		// and leave it; the next info text will be placed on a new panel anyway
		this.infoPanel.disableInteractive();
		this.next();
	}

	/**
	 * Get the content that will be shown inside the feedback / stats / score dialogue after each level was solved. CONFIG
	 * @returns {string} The text/string that will be shown.
	 */
	getFeedbackText()
	{
		/*let str = 
`${languageDict['optimumSwitchClicks'][gameLanguage]} ${this.level.calculateOptimum().toString()}
${languageDict['yourSwitchClicks'][gameLanguage]} ${this.level.stats.switchClickCtr.toString()} × ${Math.abs(scoreValues.switchClick)}P
${languageDict['yourConfirmClicks'][gameLanguage]}	${this.level.stats.confirmClickCtr.toString()} × ${Math.abs(scoreValues.wrongSolution)}P
--------------------------------
${languageDict['yourScore'][gameLanguage]} ${this.level.stats.score.toString()} / ${this.level.getBestScorePossible()}
` // Multiplication symbols: · ×
		*/

		const textSwitchClicks = LangDict.get('bestScorePossible');
		const textBestClicks = LangDict.get('optimumSwitchClicks');
		const textYourScore = LangDict.get('yourScore');

		let str = 
`${textBestClicks} ${this.level.minimalHammingDistance.toString()}

${textYourScore} ${this.level.stats.score.toString()}
`;
		if(scoreValues.switchClick != 0)
			str += `\n${textSwitchClicks} ${scoreValues.switchClick != 0 ? this.level.getBestScorePossible() : ''}`;

		return str;
	}

	/**
	 * Called when the user closes the level feedback dialogue (shown when the user clicked confirm and the level was solved correctly)
	 */
	onCloseFeedbackAlert()
	{
		JsonRPC.send("popup", {"content": "feedback", "action": "hide"})
		this.feedbackPopUp.setVisible(false);
		this.nextLevelButton.setInteractive();

		this.highlightButton(this.nextLevelButton);
	}

	/**
	 * The participant has finished the level, the feedback popup was shown and the user now intends to load the next level.
	 */
	onNextLevelButtonClicked()
	{
		this.feedbackPopUp.setVisible(false);
		this.nextLevelButton.disableInteractive();
		this.next();
	}

	// @Override
	onAlertTimer()
	{
		super.onAlertTimer();
		this.highlightButton(this.confirmButton);
	}

	// @Override
	onTimerEnd()
	{
		super.onTimerEnd();

		// Click confirm, if the player hasn't done it already
		if(!this.feedbackPopUp.isVisible() && !this.nextLevelButton.isVisible() && !this.showState && this.level != null)
		{
			console.log("Force-clicking confirm button");
			this.onConfirmButtonClicked();
			this.buttonBar.setButtonVisible(this.simulateLevelButton, false);
		}

		// Update the button that brings the user to the next stage
		// Will become interactive, after the server successfully received the timerEnd Event
		this.buttonBar.setButtonText(this.nextLevelButton, LangDict.get('next'), false);
		this.nextLevelButton.setInteractive(false);
		this.buttonBar.setButtonVisible(this.nextLevelButton, true, false);

		// Hide all unnecessary buttons
		this.buttonBar.setButtonVisible(this.simulateLevelButton, false, false);
		this.buttonBar.setButtonVisible(this.confirmButton, false, false);

		// Disable all switches and the drawing feature
		if(this.level != null)
			this.level.setSwitchesInteractive(false);
		this.draw.deactivateDrawing();
		this.buttonBar.updatePositions();
	}

	// @Override
	onTimeoutConfirmed()
	{
		// Only enable the next level button, after the server has received the end of SkillAssessment notification.
		this.nextLevelButton.setInteractive(true);
	}

	// @Override
	onCloseDialogue(gameObject)
	{
		super.onCloseDialogue(gameObject);

		if(this.popupLevelTimerEnd && this.popupLevelTimerEnd.isVisible())
		{
			this.popupLevelTimerEnd.setVisible(false);
			JsonRPC.que("popup", {"content": "levelTimerEnd", "action": "hide"});
		}
	}

	onLevelTimerEnd()
	{
		console.log("Level timer ended.");

		// Don't show popup & skip button if level is already solved or the phase timer has run out
		if(this.nextLevelButton.isVisible() || this.feedbackPopUp.isVisible())
			return;

		if('skipLevelButton' in this && this.skipLevelButton instanceof RectButton)
		{
			this.buttonBar.setButtonVisible(this.skipLevelButton, true);
			this.skipLevelButton.setInteractive();

			if(!this.slidesShown.levelTimeLimit)
			{
				this.popupLevelTimerEnd = new Alert(this, "popupLevelTimerEnd", "ok", "closeDialogue", 120);
				JsonRPC.que("popup", {"content": "levelTimerEnd", "action": "show"});
			}
		}
	}

	showFeedbackAlert()
	{
		// Show the feedback popup dialogue
		this.feedbackPopUp.setText(this.getFeedbackText());
		this.feedbackPopUp.setVisible(true);
		AniLib.popIn(this.feedbackPopUp, this);

		// Send the Feedback Shown event to the server
		// When the phase is quali, a quali pass/fail will be in the message que.
		JsonRPC.que("popup", {
			"content": "feedback", 
			"action": "show", 
			"a": this.level.stats.switchClickCtr,
			// TODO move minSwitchClick update out of popup logging endpoint
			"b": this.level.minimalHammingDistance,
			"c": this.level.stats.confirmClickCtr
		});
	}

	/**
	 * Show the next level button (hides confirm and simulateLevel button)
	 * @param {boolean} interactive True if the next button should be interactive immediately
	 */
	showNextButton(interactive)
	{
		// Hide/Disable all unnecessary inputs/text
		this.buttonBar.setButtonVisible(this.simulateLevelButton, false, false);
		this.buttonBar.setButtonVisible(this.confirmButton, false, false);

		this.buttonBar.setButtonVisible(this.nextLevelButton, true);
		this.nextLevelButton.setInteractive(interactive);
	}

	/**
	 * Check if the simulate button is shown by default.
	 * @returns True if the simulate button is shown at the level start.
	 */
	getSimulateButtonEnabled()
	{
		return [DIFFICULTY.MEDIUM, DIFFICULTY.ADVANCED].includes(this.gameMode) && mediumShowSimulateButton;
	}

	// @Override
	getLocation()
	{
		return super.getLocation() + '/' + this.levelName;
	}

	/**
	 * Start the wrong solution countdown (if configured)
	 * @returns 
	 */
	startWrongSolutionCooldown()
	{
		// Enable Stop simulation immediately if wrongSolutionCooldown is too small
		if(gamerules.wrongSolutionCooldown < 0.0001)
		{
			if(this.simulateLevelButton.isVisible())
			{
				this.simulateLevelButton.setInteractive();
				this.highlightButton(this.simulateLevelButton);
			}
			return;
		}

		// Disable all input and calculate delay
		this.setInputEnabled(false);
		let delay = gamerules.wrongSolutionCooldown * Math.pow(gamerules.wrongSolutionMultiplier, this.level.stats.confirmClickCtr-1);
		if (gamerules.wrongSolutionCooldownLimit > 0) {
			delay = Math.min(delay, gamerules.wrongSolutionCooldownLimit);
		}

		// Create the cooldown animation & start input reactivation countdown
		this.buttonBar.addCooldown(delay, function(tween) {
			if(this.simulateLevelButton.isVisible())
			{
				this.simulateLevelButton.setInteractive();
				this.highlightButton(this.simulateLevelButton);
			}
			else
				this.setInputEnabled(true);
		}.bind(this));
	}

	/**
	 * 
	 * @param {boolean} inputEnabled 
	 */
	setInputEnabled(inputEnabled)
	{
		this.level.setSwitchesInteractive(inputEnabled);
		this.buttonBar.setInteractive(inputEnabled);
	}

	// @Override
	cleanUp()
	{
		try {this.timerReminderText.destroy();} catch {}
		this.stopCountdown();
		super.cleanUp();
	}
}

GameScene.levelsToGo = -1;

// Phase Difficulty Enums
const DIFFICULTY = {
	EASY: "EASY",
	MEDIUM: "MEDIUM",
	ADVANCED: "ADVANCED",
	HARD: "HARD"
}

/**
 * CONFIG: Change these to modify the difficulty (affects wire highlighting etc) for the different phases. EASY / MEDIUM / HARD
 * 
 * Quali: 
 * Competition: 
 */
let phaseDifficulty = gamerules.phaseDifficulty

// CONFIG: Display Simulate Level Button
let mediumShowSimulateButton = gamerules.mediumShowSimulateButton;

// Cheating: Type nextLevel() inside your Browser console
var cheat = {
	skip: _cheatNotLoaded,
	solve: _cheatNotLoaded
};

var _cheatNotLoaded = () => console.log('No level loaded yet. Please enter quali or competition phase first');
