function Show-Board {
    param([string[][]]$Board)
    $Board | ForEach-Object {
        ($_ -join ' | ') -replace ' ', '_'
    }
}

function Player-Turn {
    param([string]$Player)
    $invalid = $true
    while ($invalid) {
        try {
            $input = Read-Host "Player $Player, your turn. Please input your move as 'x,y'"
            $x, $y = $input.Split(',')
            if ($null -eq $Global:Board[$x][$y]) {
                $Global:Board[$x][$y] = $Player
                $invalid = $false
            } else {
                Write-Host "Invalid move. Try again."
            }
        } catch {
            Write-Host "Invalid input. Try again."
        }
    }
}

function Check-Winner {
    param([string]$Player)

    for ($i = 0; $i -lt 3; $i++) {
        if (($Global:Board[$i][0] -eq $Player) -and ($Global:Board[$i][1] -eq $Player) -and ($Global:Board[$i][2] -eq $Player)) {
            return $true
        }

        if (($Global:Board[0][$i] -eq $Player) -and ($Global:Board[1][$i] -eq $Player) -and ($Global:Board[2][$i] -eq $Player)) {
            return $true
        }
    }

    if (($Global:Board[0][0] -eq $Player) -and ($Global:Board[1][1] -eq $Player) -and ($Global:Board[2][2] -eq $Player)) {
        return $true
    }

    if (($Global:Board[0][2] -eq $Player) -and ($Global:Board[1][1] -eq $Player) -and ($Global:Board[2][0] -eq $Player)) {
        return $true
    }

    return $false
}

$Global:Board = @(@(,$null,$null,$null),@($null,$null,$null),@($null,$null,$null))
$players = @('X', 'O')
$turns = 0

while ($turns -lt 9) {
    Show-Board -Board $Global:Board

    $currentPlayer = $players[$turns % 2]
    Player-Turn -Player $currentPlayer

    if (Check-Winner -Player $currentPlayer) {
        Show-Board -Board $Global:Board
        Write-Host "Player $currentPlayer wins!"
        exit
    }

    $turns++
}

Show-Board -Board $Global:Board
Write-Host "It's a draw!"
