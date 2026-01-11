/**
 * 
 */
class CompetitionScene extends GameScene
{
	/**
	 * @param {string} phase Name of the phase, for e.g. quali or competition
	 */
	constructor(phase = 'Competition')
	{
		super(phase);
	}

	// @Override
	initChildren()
	{
		this.skipLevelPopUp = new Alert(this, 'skipLevel', 'clear', 'PopUp_Alert_introSkipLevel');
		this.skipLevelPopUp.setVisible(false);

		// Register the event handlers for every button 
		this.registerClickListener('PopUp_Alert_introSkipLevel', this.onCloseIntroSkipLevelAlert);
		this.registerClickListener('SkipLevelButton', this.onSkipLevelButtonClicked);
	}

	// @Override
	initButtons()
	{
		super.initButtons();

		// create button for skipping levels
		this.skipLevelButton = new RectButton(this, this.confirmButton.rect.x - this.confirmButton.rect.displayWidth / 2 - 20, this.confirmButton.y, 'skipLevelTXT', 'right', 'SkipLevelButton');
		this.skipLevelButton.setDepth(35);
		this.buttonBar.add(this.skipLevelButton);

		// Show the skip level button at level start if configured, or hide it if config is `"struggling"` or `"never"`
		if(gamerules.competitionShowSkipButton == "always")
		{
			this.buttonBar.setButtonVisible(this.skipLevelButton, true);
			this.skipLevelButton.setInteractive();
		}
		else
			this.buttonBar.setButtonVisible(this.skipLevelButton, false);
	}
	
	// @Override
	cleanLast()
	{
		// Do not hide the skip level button if it is set to always show
		if(gamerules.competitionShowSkipButton != "always")
			this.buttonBar.setButtonVisible(this.skipLevelButton, false);
		
		super.cleanLast();
	}

	// @Override
	showNextButton(interactive)
	{
		this.buttonBar.setButtonVisible(this.skipLevelButton, false);
		super.showNextButton(interactive);
	}

	// @Override
	onSwitchClicked(gameObject)
	{
		super.onSwitchClicked(gameObject);
	}

	/**
	 * Called when the user closes the SkipLevel dialogue.
	 */
	onCloseIntroSkipLevelAlert()
	{
		JsonRPC.send("popup", {"content": "introSkip", "action": "hide"})

		this.skipLevelPopUp.setVisible(false);

		this.level.setSwitchesInteractive(true);
		this.setDrawingEnabled(true);

		this.skipLevelButton.setInteractive();

		AniLib.clearAnimations(this.skipLevelButton.getObjects(), this);
	}

	/**
	 * The user has pressed the button to skip this level. The button is only shown after 2 confirm clicks or 15 switch clicks
	 */
	onSkipLevelButtonClicked(gameObject)
	{
		JsonRPC.send("skip", {})
		// log information about circuit 
		
		AniLib.clearAnimations(this.simulateLevelButton.getObjects(), this);
		this.skipLevelButton.disableInteractive();
		this.confirmButton.disableInteractive();
		this.next();
	}

	// @Override
	onSimulateButtonClicked(writeLogData = true)
	{
		super.onSimulateButtonClicked(writeLogData);

		// Also disable the skip level button while simulating
		if(this.showState)
			this.skipLevelButton.disableInteractive();
		else
			this.skipLevelButton.setInteractive();
	}

	/**
	 * Introduce the skip level button after the user pressed confirm 2 times or switches 15 times.
	 */
	introduceSkipLevelButton()
	{
		// Only show the skip level button, if enabled
		if(gamerules.competitionShowSkipButton == "never")
			return;

		JsonRPC.send("popup", {"content": "introSkip", "action": "show"});

		this.skipLevelPopUp.setVisible(true);
		this.skipLevelButton.setInteractive();
		this.buttonBar.setButtonVisible(this.skipLevelButton, true);
		
		// this.skipLevelBackground.setVisible(true);
		// deactivate interactive objects 
		this.level.setSwitchesInteractive(false);
		this.setDrawingEnabled(false);

		this.confirmButton.disableInteractive();
		this.skipLevelButton.disableInteractive();
		this.simulateLevelButton.disableInteractive();

		AniLib.clearAnimations(this.simulateLevelButton.getObjects(), this);
		AniLib.scaleUpDownAnimation(this.skipLevelButton.getObjects(), 1.1, 1.1, 2000, this);
	}
	
	// @Override
	updateScore(operationName)
	{
		//const MAX_SWITCH_CLICKS_BEFORE_HELP = 15;

		// Update the score, then check if skip condition matches
		super.updateScore(operationName);

		// ask player if he wants to skip the level
		if((this.skipLevelButton == null || !this.skipLevelButton.isVisible()) && !this.solved)
			if(this.level.stats.score <= 0)// || this.level.stats.switchClickCtr > MAX_SWITCH_CLICKS_BEFORE_HELP)
				this.introduceSkipLevelButton();
	}

	beforeSuspendUI()
	{
		super.beforeSuspendUI();

		// When clearing the tweens in super the skip button will become interactive again
		// because onComplete is called. Therefore the button could be clicked again 
		// before the slide change
		this.skipLevelButton.disableInteractive();
	}
}
