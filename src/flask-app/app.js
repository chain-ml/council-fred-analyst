document.addEventListener('DOMContentLoaded', function () {
  // Initialize CodeMirror
  var editor = CodeMirror.fromTextArea(document.getElementById("code"), {
    mode: "python",
    lineNumbers: true,
    theme: "dracula",
  });

  var logs_console = CodeMirror.fromTextArea(document.getElementById("logs"), {
    mode: "text",
    lineNumbers: false,
    theme: "dracula",
    lineWrapping: true,
  });

  fetch('http://127.0.0.1:5000/reset', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: ''
  })

  // Event listener for executing the code
  function executeCode() {
    var code = editor.getValue(); // Assuming you have an initialized CodeMirror editor

    fetch('http://127.0.0.1:5000/execute', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: 'code=' + encodeURIComponent(code)
    })
      .then(response => response.text())
      .then(result => {
        console.log('Code executed:', result);
        // Handle the response/result as needed
      })
      .catch(error => {
        console.error('Error executing code:', error);
        // Handle the error
      });
  }


  // Event listener for automatic reloading on file change
  function reloadOnChange() {
    var fileUrl = 'http://127.0.0.1:5000/get_code';  // Replace with the URL of your file on the server

    var xhr = new XMLHttpRequest();
    xhr.onload = function () {
      if (xhr.status === 200) {
        var fileContent = xhr.responseText;
        editor.setValue(fileContent);
      }
    };

    xhr.open('GET', fileUrl, true);
    xhr.send();
  }

  function clearCode() {
    // Post the code in the editor to the server first
    var code = '';
    editor.setValue(code)

    fetch('http://127.0.0.1:5000/post_code', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: 'code=' + encodeURIComponent(code)
    })
      .then(response => response.text())
      .then(result => {
        console.log('Code executed:', result);
        // Handle the response/result as needed
      })
      .catch(error => {
        console.error('Error executing code:', error);
        // Handle the error
      });

  }

  // Attach event listeners
  // document.getElementById("executeButton").addEventListener("click", executeCode);
  // document.getElementById("refreshButton").addEventListener("click", clearCode);
  reloadOnChange();

  var chatContainer = document.getElementById('chatContainer');
  var messageInput = document.getElementById('messageInput');
  var sendMessageButton = document.getElementById('sendMessageButton');

  function addMessage(message, isUser) {

    var messageElement = document.createElement('div');
    messageElement.classList.add('message');

    var messageContent = document.createElement('div');
    messageContent.classList.add('message-content');

    if (isUser) {
      messageElement.classList.add('user-message');
      messageContent.textContent = '\uD83D\uDC64 ' + message; // Add human emoji escape sequence
    } else {
      messageElement.classList.add('assistant-message');
      messageContent.textContent = '\uD83E\uDD16 ' + message; // Add AI assistant emoji escape sequence
    }

    messageElement.appendChild(messageContent);
    chatContainer.appendChild(messageElement);

    // Scroll to the bottom of the chat container
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }


  function handleUserMessage() {

    // Post the code in the editor to the server first
    var code = editor.getValue(); // Assuming you have an initialized CodeMirror editor

    fetch('http://127.0.0.1:5000/post_code', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: 'code=' + encodeURIComponent(code)
    })
      .then(response => response.text())
      .then(result => {
        console.log('Code executed:', result);
        // Handle the response/result as needed
      })
      .catch(error => {
        console.error('Error executing code:', error);
        // Handle the error
      });


    var message = messageInput.value.trim();
    if (message !== '') {
      addMessage(message, true); // Add the user's message to the chat interface
      messageInput.value = ''; // Clear the input field

      // Send the user message to the server
      fetch('http://127.0.0.1:5000/handle_user_message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'message=' + encodeURIComponent(message)
      })
        .then(response => response.json())
        .then(result => {
          // Handle the response from the server
          addMessage(result['message'], false); // Add the AI assistant's response to the chat interface
          logs_console.setValue(result['message'])
          editor.setValue(result['code'])
          console.log(result['code'])

          // reloadOnChange();
        })
        .catch(error => {
          console.error('Error sending user message:', error);
          // Handle the error
        });
    }
  }

  const logsSource = new EventSource('http://127.0.0.1:5000/latest_log_stream');

  logsSource.onmessage = function (event) {
    // Update the UI with the latest log message
    const latestLogMessage = event.data;
    console.log(latestLogMessage);
    // Process the latest log message as needed
    logs_console.setValue(latestLogMessage);
    // Scroll to the bottom of the logs_console
    logs_console.scrollIntoView({ line: logs_console.lastLine(), char: 0 }, 100);
  };


  sendMessageButton.addEventListener('click', handleUserMessage);
  messageInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      handleUserMessage();
    }
  });
});

