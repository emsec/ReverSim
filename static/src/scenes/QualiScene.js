/**
 * Show the player a bunch of levels/tasks which need to be solved, in order qualify for 
 * the Competition Phase.
 * If the player makes to many mistakes, he will be send back to ElementIntroduction.
 */
class QualiScene extends GameScene
{
	constructor()
	{
		super('Quali');
		this.introduceQualiElements = true;
		this.qualifiedForComp = true;
	}

	initChildren()
	{
		let params = new URLSearchParams(document.location.search);
		// Set the cookie, if query param onsite is not set
		if(params.get('onsite') != "1")
			CookieUtils.setCookie(userCookieName, pseudonym);

		// Register the event handlers for every button 
		this.registerClickListener('PopUp_Alert_introConfirm', this.onCloseIntroConfirmAlert);
	}

	loadLevel(levelStr) 
	{
		super.loadLevel(levelStr);

		// Show introConfirm dialogue (only if the timer has not run out)
		if(!this.slidesShown.introConfirm && !this.nextLevelButton.isVisible())
			this.introduceConfirmButton();
	}

	/**
	 * Called after the user closes the confirm button introduction dialogue.
	 */
	onCloseIntroConfirmAlert()
	{
		this.introduceConfirmButtonPopUp.setVisible(false);

		JsonRPC.que("popup", {"content": "introConfirm", "action": "hide"})

		this.slidesShown.introConfirm = true;

		// activate objects again (if the timer has not run out in the meantime)
		if(!this.nextLevelButton.isVisible())
		{
			this.level.setSwitchesInteractive(true);
			this.setDrawingEnabled(true);
			this.confirmButton.setInteractive();

			AniLib.clearAnimations(this.confirmButton.getObjects(), this);
		}
	}

	/**
	 * Called when the user loads the first level. This popup will explain the confirm button.
	 */
	introduceConfirmButton() 
	{
		this.slidesShown.introConfirm = true;
		JsonRPC.que("popup", {"content": "introConfirm", "action": "show"});

		// create Alert explaining the 'Confirm' Button
		this.introduceConfirmButtonPopUp = new Alert(this, 'introduceConfirmButton', 'hereWeGo', 'PopUp_Alert_introConfirm');

		// disable interactivity of some objects
		this.level.setSwitchesInteractive(false);
		this.setDrawingEnabled(false);
		this.confirmButton.disableInteractive();

		// Highlight the confirm button
		AniLib.scaleUpDownAnimation(this.confirmButton.getObjects(), 1.1, 1.1, 2000, this);
	}

	/**
	 * Get the content that will be shown inside the feedback / stats / score dialogue after each level was solved.
	 * 
	 * If the user failed one level, it will also contain the explanation why the user is send back to ElementIntroduction.
	 * @returns {string} The text/string that will be shown. 
	 */
	getFeedbackText()
	{
		// Return the standard text if quali condition is passed
		if(this.isQualifiedForComp())
			return super.getFeedbackText();
		
		// Return the quali failed message otherwise and update ui
		this.feedbackPopUp.button.setTextLabel('gotIt');
		return LangDict.get('notQualified') + '\n\n' + super.getFeedbackText();
	}

	/**
	 * Check if the user made to many switch clicks / confirm clicks.
	 * 
	 * If the user failed this level, a flag will be set that gets read by onHookClicked() which will then send the player back to the ElementIntroduction.
	 * A log entry will be written every time the user passes or fails a level.
	 * @returns {boolean} True if the user passed this level, false otherwise.
	 */
	isQualifiedForComp()
	{
		this.qualifiedForComp = !this.checkQualiCondition();
		JsonRPC.que("qualiState", {"failed": !this.qualifiedForComp});
		return this.qualifiedForComp;
	}

	/**
	 * Implement your logic here, that checks if the player failed the Quali phase.
	 * Will be checked after every confirm click, switch click and end simulation
	 * @returns True if the user failed the quali level (too many switch or confirm clicks)
	 */
	checkQualiCondition()
	{
		const isSolved = super.getSolvingState();
		return this.level.stats.confirmClickCtr >= 2 && !isSolved;
	}

	onCloseFeedbackAlert()
	{
		// When the user failed the quali phase, send him to ElementIntro after
		// the popUp is closed. Otherwise proceed as usual.
		if(this.qualifiedForComp)
			super.onCloseFeedbackAlert();
		else
		{
			// User is not qualified, send him back to ElementIntro
			// Disable the button to prevent click spam
			this.feedbackPopUp.button.disableInteractive();
			this.next();
		}
	}

	// @Override
	onSwitchClicked(gameObject)
	{
		super.onSwitchClicked(gameObject);
		if(this.checkQualiCondition())
			this.onConfirmButtonClicked(null);
	}

	// @Override
	getSolvingState()
	{
		// Return True when the player failed the quali phase, to be able to show the 
		// level feedback dialogue.
		if(this.checkQualiCondition())
			return true;

		return super.getSolvingState();
	}

	// @Override
	onSimulateButtonClicked()
	{
		super.onSimulateButtonClicked();

		// Throw back the player after clicking simulate
		if(!this.showState && this.checkQualiCondition())
			this.onConfirmButtonClicked(null);
	}
}