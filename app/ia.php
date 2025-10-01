<?php

require __DIR__ . '/../vendor/autoload.php';

use OllamaIAService\OllamaIAService;

$iaService = new OllamaIAService();

echo 'Pregunta para la IA:'. PHP_EOL;

while(true){
    $input = readline('> ');

    if($input === 'exit' || $input === ''){
        break;
    }    

    $response = $iaService->getResponse($input);

    echo $response . PHP_EOL;
}