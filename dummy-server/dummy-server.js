const WebSocket = require('ws');

const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', ws => {
    console.log('Client connected');

    ws.on('message', message => {
        const data = JSON.parse(message);
        console.log(`Received: ${data.payload} 
    from client ${data.clientId}`);
        // Broadcast the message to all connected clients


    });

    ws.on('close', () => {
        console.log('Client disconnected');
    });
});
setInterval(() => {
    let dummyData = {
        field1: Math.random() * 100,
        stressLevels: Math.sin(Math.random()) * 100,
        field3: Math.random() * 100,
        field4: Math.random() * 100,
    }
    wss.clients.forEach(client => {

        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(dummyData));
        }
    });
}, 50)