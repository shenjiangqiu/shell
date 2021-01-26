#include <cstdlib>
#include <iostream>
#include <string>
#include "vector"

std::vector<std::string> split_into_commands(const std::string &command, int from) {
    if (from >= command.size()) {
        return std::vector<std::string>({""});
    } else {
        auto &&substring = command.substr(from, command.size());
        for (int i = 0; i < substring.size(); i++) {
            if (substring[i] == '|') {
                auto remain = split_into_commands(command, from + i + 1);
                if (i == 0) {
                    remain.insert(remain.begin(), "");
                } else {
                    remain.insert(remain.begin(), substring.substr(0, i));
                }
                return remain;
            }
        }
        //cannot find '|'
        return std::vector<std::string>({substring});

    }
}

void parse_and_run_command(const std::string &command) {
    /* TODO: Implement this. */
    /* Note that this is not the correct way to test for the exit command.
       For example the command "   exit  " should also exit your shell.
     */
    auto vec = split_into_commands(command, 0);
    int i = 0;
    for (auto &&v:vec) {
        std::cout << i++ << " " << v << std::endl;
    }
    if (command == "exit") {
        exit(0);
    }

    std::cerr << "Not implemented.\n";
}

int main(void) {
    std::string command;
    std::cout << "> ";
    while (std::getline(std::cin, command)) {
        parse_and_run_command(command);
        std::cout << "> ";
    }
    return 0;
}
