#include "vector"
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include "unistd.h"
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include "cstring"
#include <sys/types.h>
#include <sys/wait.h>

struct CMD {
    std::vector<std::string> cmd{};
    bool is_input_redirect{false};
    std::string input_redirect_file{};
    bool is_output_redirect{false};
    std::string output_redirect_file{};

    bool is_read_previous{false};
    bool is_send_next{false};
    bool error{false};
    std::string error_message{};

    void print() {
        for (auto c:cmd) {
            std::cout << c << ",";
        }
        std::cout << std::endl;
        std::cout << is_input_redirect << " " << input_redirect_file << "," << is_output_redirect << " "
                  << output_redirect_file << ",";
        std::cout << is_read_previous << " " << is_send_next << std::endl;
        std::cout << error << " " << error_message << std::endl;
    }
};

std::vector<std::string> split_into_commands(const std::string &command,
                                             unsigned from) {
    if (from >= command.size()) {
        return std::vector<std::string>({""});
    } else {
        auto &&substring = command.substr(from, command.size());
        for (unsigned i = 0; i < substring.size(); i++) {
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
        // cannot find '|'
        return std::vector<std::string>({substring});
    }
}

std::vector<std::string> split_single_command(const std::string &single_cmd) {
    std::stringstream s(single_cmd);
    std::string temp;
    std::vector<std::string> out;
    while (s >> temp) {
        if (!temp.empty()) {
            out.push_back(temp);
        }
    }
    return out;
}

std::vector<CMD> build_cmd(const std::vector<std::string> &command) {
    std::vector<CMD> out;
    unsigned index = 0;
    for (const auto &i : command) {
        auto &&v = split_single_command(i);
        CMD cmd;
        if (index != command.size() - 1 and command.size() != 1) {
            cmd.is_send_next = true;
        }
        if (index != 0 and command.size() != 1) {
            cmd.is_read_previous = true;
        }
        index++;
        for (auto j = 0u; j < v.size(); j++) {
            if (v[j] == std::string("<")) {
                if (j < v.size() - 1) {
                    auto input_file = v[j + 1];
                    j++;
                    cmd.is_input_redirect = true;
                    cmd.input_redirect_file = input_file;
                    continue;
                } else {
                    cmd.error = true;
                    cmd.error_message = "need input file name after <";
                    break;
                }
            }
            if (v[j] == std::string(">")) {
                if (j < v.size() - 1) {
                    auto input_file = v[j + 1];
                    j++;
                    cmd.is_output_redirect = true;
                    cmd.output_redirect_file = input_file;
                    continue;
                } else {
                    cmd.error = true;
                    cmd.error_message = "need output file name after >";
                    break;
                }
            }

            //normal command
            cmd.cmd.push_back(v[j]);


        }//end parse the cmd
        out.push_back(cmd);
    }

    return out;

}


void parse_and_run_command(const std::string &command) {

    /* Note that this is not the correct way to test for the exit command.
       For example the command "   exit  " should also exit your shell.
     */
    int default_input = dup(0);
    if (command == "exit") {
        exit(0);
    }
    if (command[0] == '#') {
        exit(0);
    }
    auto vec = split_into_commands(command, 0);


    auto ret = build_cmd(vec);

    for (auto &&c : ret) {
        if (c.error) {
            std::cerr << "Invalid command" << std::endl;
            return;
        }

    }
    //all good, start to execute the commands
    std::vector<int> pids;
    int m_pip[2] = {0};

    for (auto &&c:ret) {


        if (c.is_send_next) {
            if (-1 == pipe(m_pip)) {
                std::cerr << "cannot creat the pip\n";
                return;
            }
        }

        int pid = fork();
        if (pid == 0) {
            if (c.is_send_next) {
                dup2(m_pip[1], 1);
                close(m_pip[1]);
                close(m_pip[0]);
            }


            //the sub process handle the redirection
            if (c.is_input_redirect) {
                auto filename = c.input_redirect_file;
                int fd_in = open(filename.c_str(), O_RDONLY);
                if (-1 == fd_in) {
                    perror(nullptr);
                    exit(-1);
                }
                close(0);
                dup2(fd_in, 0);
                close(fd_in);
            }
            if (c.is_output_redirect) {
                auto filename = c.output_redirect_file;
                int fd_out = open(filename.c_str(), O_WRONLY | O_TRUNC | O_CREAT);
                if (-1 == fd_out) {
                    perror(nullptr);
                    exit(-1);
                }
                close(1);
                dup2(fd_out, 1);
                close(fd_out);
            }
            //execute the process
            char *args[100] = {nullptr};
            for (auto i = 0u; i < c.cmd.size(); i++) {
                //args[i - 1] = c.cmd[i].c_str();
                args[i] = new char[100];
                strcpy(args[i], c.cmd[i].c_str());
            }
            //i==c.cmd.size;

            if (-1 == execv(c.cmd[0].c_str(), args)) {
                perror(nullptr);
                exit(0);
            }


        } else {
            if (c.is_send_next) {
                close(0);
                dup2(m_pip[0], 0);
                close(m_pip[1]);
                close(m_pip[0]);
            }

            std::cout << pid << " is running" << std::endl;
            pids.push_back(pid);
        }

    }

    int ii = 0;

    for (
        auto i
            :pids) {
        int status;
        auto result = waitpid(i, &status, 0);
        if (result == -1) {
            perror(nullptr);
            return;
        }
        for (
            const auto &c
                :ret[ii].cmd) {
            std::cout << c << " ";
        }

        std::cout << " exit status: " << status <<
                  std::endl;
        ii++;
        dup2(default_input, 0);
        close(default_input);
    }

}

int main(void) {
    std::string command;
    std::cout << "> ";
    while (std::getline(std::cin, command)) {
        parse_and_run_command(command);
        std::cout << "> ";
        std::cout.flush();
    }
    return 0;
}
